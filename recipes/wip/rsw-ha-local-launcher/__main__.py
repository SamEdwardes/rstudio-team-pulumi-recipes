"""An AWS Python Pulumi program"""

import os
from textwrap import dedent
from typing import Dict, Optional
import json
import subprocess

import pulumi
from pulumi_aws import ec2, efs, rds, ssm, iam
from pulumi_command import remote

from src.helpers import BaseConfig, decode_key, get_key_pair


def make_security_group(resource_id: str, tags: Dict):
    """
    See the group made by Katie for reference:
        - sg-04517fafba8d963c0 - world-accessible-team-editable-katie
        - https://us-east-1.console.aws.amazon.com/ec2/v2/home?region=us-east-1#SecurityGroup:securityGroupId=sg-04517fafba8d963c0
    """
    sg = ec2.SecurityGroup(
        resource_id,
        description="Sam security group for Pulumi deployment",
        ingress=[
            {"protocol": "TCP", "from_port": 22, "to_port": 22, 'cidr_blocks': ['0.0.0.0/0'], "description": "SSH"},
            {"protocol": "TCP", "from_port": 8787, "to_port": 8787, 'cidr_blocks': ['0.0.0.0/0'], "description": "RSW"},
            {"protocol": "TCP", "from_port": 2049, "to_port": 2049, 'cidr_blocks': ['0.0.0.0/0'], "description": "NSF"},
            {"protocol": "TCP", "from_port": 80, "to_port": 80, 'cidr_blocks': ['0.0.0.0/0'], "description": "HTTP"},
            {"protocol": "TCP", "from_port": 5432, "to_port": 5432, 'cidr_blocks': ['0.0.0.0/0'], "description": "POSTGRESQL"},
        ],
        egress=[
            {"protocol": "All", "from_port": -1, "to_port": -1, 'cidr_blocks': ['0.0.0.0/0'], "description": "Allow all outbout traffic"},
        ],
        tags=tags
    )
    return sg


def make_rsw_server(name: str, config: BaseConfig, tags: Dict):
    # Stand up a server.
    server = ec2.Instance(
        f"rstudio-workbench-{name}",
        instance_type=config.ec2_size,
        vpc_security_group_ids=config.vpc_group_ids,
        ami=config.ami_id,
        tags=tags,
        key_name=config.key_pair.key_name
    )
    
    # Export final pulumi variables.
    pulumi.export(f'rsw_{name}_public_ip', server.public_ip)
    pulumi.export(f'rsw_{name}_public_dns', server.public_dns)
    pulumi.export(f'rsw_{name}_subnet_id', server.subnet_id)

    # Set up a connection
    connection = remote.ConnectionArgs(
        host=server.public_dns, 
        user="ubuntu", 
        private_key=config.private_key
    )

    _install_justfile = remote.Command(
        f"server-{name}-install-justfile", 
        create=dedent(f"""
        curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin;
        echo 'export PATH="$PATH:$HOME/bin"' >> ~/.bashrc;
        """).strip(), 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[server])
    )

    _copy_justfile = remote.CopyFile(
        f"server-{name}-copy-justfile",  
        local_path="templates/justfile", 
        remote_path='justfile', 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[server])
    )

    return server


def main():
    tags = {
        "rs:environment": "development",
        "rs:owner": "sam.edwardes@rstudio.com",
        "rs:project": "solutions",
    }

    # Set up keys.
    config = pulumi.Config()
    key_pair = get_key_pair(config)
    private_key = config.require_secret('privateKey').apply(decode_key)

    # Make servers.
    rsw_security_group = make_security_group(
        resource_id="rsw-ha-sg",
        tags=tags | {"Name": "samedwardes"}
    )

    rsw_config = BaseConfig(
        key_pair=key_pair, 
        private_key=private_key, 
        vpc_group_ids=[rsw_security_group.id]
    )

    rsw_server_1 = make_rsw_server("1", config=rsw_config, tags=tags | {"Name": "rsw-1"})
    rsw_server_2 = make_rsw_server("2", config=rsw_config, tags=tags | {"Name": "rsw-2"})

    # Create EFS
    file_system = efs.FileSystem("efs-rsw-ha",tags= tags | {"Name": "rsw-ha-efs"})
    pulumi.export("efs_id", file_system.id)

    # Create a mount target. Assumes that the servers are on the same subnet id.
    mount_target = efs.MountTarget(
        f"mount-target-rsw",
        file_system_id=file_system.id,
        subnet_id=rsw_server_1.subnet_id,
        security_groups=[rsw_security_group.id]
    )

    # Create a postgresql database.
    db = rds.Instance(
        "rsw-db",
        instance_class="db.t3.micro",
        allocated_storage=5,
        username="rswadmin",
        password="password",
        db_name="rsw_data",
        engine="postgres",
        publicly_accessible=True,
        skip_final_snapshot=True,
        tags=tags | {"Name": "samedwardes-rsw-db"},
        vpc_security_group_ids=[rsw_security_group.id]
    )
    pulumi.export("db_port", db.port)
    pulumi.export("db_address", db.address)
    pulumi.export("db_endpoint", db.endpoint)
    pulumi.export("db_name", db.name)
    pulumi.export("db_domain", db.domain)

    # --------------------------------------------------------------------------
    # Set environment variables on each server
    # --------------------------------------------------------------------------
    for count, server in enumerate([rsw_server_1, rsw_server_2]):
        count += 1

        connection = remote.ConnectionArgs(
            host=server.public_dns, 
            user="ubuntu", 
            private_key=private_key
        )

        _dot_env_command = pulumi.Output.concat(
            'echo "export SERVER_IP_ADDRESS=', server.public_ip, '" > .env;\n',
            'echo "export DB_ADDRESS=',        db.address,       '" >> .env;\n',
            'echo "export EFS_ID=',            file_system.id,   '" >> .env;\n',
            'echo "export RSW_LICENSE=',       os.getenv("RSW_LICENSE"), '" >> .env;',
        )

        _set_env = remote.Command(
            f"server-{count}--set-env", 
            create=_dot_env_command, 
            connection=connection, 
            opts=pulumi.ResourceOptions(depends_on=[server, db, file_system])
        )


main()
