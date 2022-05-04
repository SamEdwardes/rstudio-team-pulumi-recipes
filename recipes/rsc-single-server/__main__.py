"""An AWS Python Pulumi program"""

import os
from pathlib import Path
from textwrap import dedent
from typing import Dict, Optional, List
import json
import subprocess

import pulumi
from pulumi_aws import ec2, efs, rds, ssm, iam
from pulumi_command import remote


def get_private_key(file_path: str) -> str:
    path = Path(file_path)
    if path.exists() == False:
        path = path.expanduser()
    with open(path, mode="r") as f:
        private_key = f.read()
    return private_key


def make_rsc_server(
    tags: Dict, 
    key_pair: ec2.KeyPair, 
    vpc_group_ids: List[str]
):
    # Stand up a server.
    server = ec2.Instance(
        f"rstudio-connect",
        instance_type="t3.medium",
        vpc_security_group_ids=vpc_group_ids,
        ami="ami-0fb653ca2d3203ac1",  # Ubuntu Server 20.04 LTS (HVM), SSD Volume Type
        tags=tags,
        key_name=key_pair.key_name
    )
    
    # Export final pulumi variables.
    pulumi.export(f'rsc_public_ip', server.public_ip)
    pulumi.export(f'rsc_public_dns', server.public_dns)
    pulumi.export(f'rsc_subnet_id', server.subnet_id)

    return server


def main():
    # --------------------------------------------------------------------------
    # Tags to apply to all resources.
    # --------------------------------------------------------------------------
    tags = {
        "rs:environment": "development",
        "rs:owner": "sam.edwardes@rstudio.com",
        "rs:project": "solutions",
    }

    # --------------------------------------------------------------------------
    # Set up keys.
    # --------------------------------------------------------------------------
    print(os.getenv("AWS_SSH_KEY_ID"))
    key_pair = ec2.get_key_pair(key_pair_id=os.getenv("AWS_SSH_KEY_ID"))
    private_key = get_private_key(os.getenv("AWS_PRIVATE_KEY_PATH"))
    
    # --------------------------------------------------------------------------
    # Make security groups
    # --------------------------------------------------------------------------
    rsc_security_group = ec2.SecurityGroup(
        "rsc-sg",
        description="Sam security group for Pulumi deployment",
        ingress=[
            {"protocol": "TCP", "from_port": 22, "to_port": 22, 'cidr_blocks': ['0.0.0.0/0'], "description": "SSH"},
            {"protocol": "TCP", "from_port": 3939, "to_port": 3939, 'cidr_blocks': ['0.0.0.0/0'], "description": "RSC"},
            {"protocol": "TCP", "from_port": 80, "to_port": 80, 'cidr_blocks': ['0.0.0.0/0'], "description": "HTTP"},
        ],
        egress=[
            {"protocol": "All", "from_port": -1, "to_port": -1, 'cidr_blocks': ['0.0.0.0/0'], "description": "Allow all outbout traffic"},
        ],
        tags=tags
    )
    
    # --------------------------------------------------------------------------
    # Stand up the servers
    # --------------------------------------------------------------------------
    rsc_server = make_rsc_server(
        tags=tags | {"Name": "samedwardes-rsc"},
        key_pair=key_pair,
        vpc_group_ids=[rsc_security_group.id]
    )

    # --------------------------------------------------------------------------
    # Install required software one each server
    # --------------------------------------------------------------------------
    connection = remote.ConnectionArgs(
        host=rsc_server.public_dns, 
        user="ubuntu", 
        private_key=private_key
    )
    name = "rsc_server"

    _set_env = remote.Command(
        f"server-{name}-set-env", 
        create=pulumi.Output.concat(
            'echo "export SERVER_IP_ADDRESS=', rsc_server.public_ip,         '" > .env;\n',
            'echo "export RSC_LICENSE=',       os.getenv("RSC_LICENSE"), '" >> .env;',
        ), 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsc_server])
    )

    _install_justfile = remote.Command(
        f"server-{name}-install-justfile",
        create="\n".join([
            """curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin;""",
            """echo 'export PATH="$PATH:$HOME/bin"' >> ~/.bashrc;"""
        ]),
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsc_server])
    )

    _copy_justfile = remote.CopyFile(
        f"server-{name}--copy-justfile",  
        local_path="templates/justfile", 
        remote_path='justfile', 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsc_server])
    )
    
    _build_rsc = remote.Command(
        f"server-{name}-build-rsc", 
        create="""export PATH="$PATH:$HOME/bin"; just build-rsc""", 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[_set_env, _install_justfile, _copy_justfile])
    )


main()
