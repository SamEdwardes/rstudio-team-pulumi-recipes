from dataclasses import dataclass, field
from pathlib import Path

import pulumi
import pulumi_tls as tls
import requests
import jinja2
from pulumi_aws import ec2, fsx
from pulumi_command import remote
from rich import print, inspect
import hashlib
from Crypto.PublicKey import RSA

# Setup pulumi configuration
config = pulumi.Config()

@dataclass 
class ConfigValues:
    email: str = field(default_factory=lambda: config.require("email"))
    rsw_license: str = field(default_factory=lambda: config.require("rsw_license"))
    public_key: str = field(default_factory=lambda: config.require("public_key"))


CONFIG_VALUES = ConfigValues()
TAGS = {
    "rs:environment": "development",
    "rs:owner": CONFIG_VALUES.email,
    "rs:project": "solutions",
}

def create_template(path: str) -> jinja2.Template:
    with open(path, 'r') as f:
        template = jinja2.Template(f.read())
    return template


def hash_file(path: str) -> pulumi.Output:
    with open(path, mode="r") as f:
        text = f.read()
    hash_str = hashlib.sha224(bytes(text, encoding='utf-8')).hexdigest()
    return pulumi.Output.concat(hash_str)


def main():
    # --------------------------------------------------------------------------
    # Make security groups
    # --------------------------------------------------------------------------
    security_group = ec2.SecurityGroup(
        "security group",
        description= CONFIG_VALUES.email + " security group for Pulumi deployment",
        ingress=[
            {"protocol": "TCP", "from_port": 22, "to_port": 22, 'cidr_blocks': ['0.0.0.0/0'], "description": "SSH"},
            {"protocol": "TCP", "from_port": 8787, "to_port": 8787, 'cidr_blocks': ['0.0.0.0/0'], "description": "RSW"},
            {"protocol": "TCP", "from_port": 443, "to_port": 443, 'cidr_blocks': ['0.0.0.0/0'], "description": "HTTPS"},
            {"protocol": "TCP", "from_port": 80, "to_port": 80, 'cidr_blocks': ['0.0.0.0/0'], "description": "HTTP"},
            {"protocol": "TCP", "from_port": 998, "to_port": 998, 'cidr_blocks': ['0.0.0.0/0'], "description": "LUSTRE"},
        ],
        egress=[
            {"protocol": "All", "from_port": -1, "to_port": -1, 'cidr_blocks': ['0.0.0.0/0'], "description": "Allow all outbound traffic"},
        ],
        tags=TAGS | {"Name": f"{CONFIG_VALUES.email}-rsw-single-server"},
    )

    # --------------------------------------------------------------------------
    # Stand up the servers
    # --------------------------------------------------------------------------
    key_pair = ec2.KeyPair(
        "ec2 key pair",
        key_name="samedwardes-keypair-for-pulumi",
        public_key=CONFIG_VALUES.public_key,
        tags=TAGS | {"Name": f"{CONFIG_VALUES.email}-key-pair"},
    )

    # Ubuntu Server 20.04 LTS (HVM), SSD Volume Type for us-east-2
    ami_id = "ami-0fb653ca2d3203ac1"

    rsw_server = ec2.Instance(
        f"rstudio workbench server",
        instance_type="t3.medium",
        vpc_security_group_ids=[security_group.id],
        ami=ami_id,                 
        tags=TAGS | {"Name": f"{CONFIG_VALUES.email}-rsw-server"},
        key_name=key_pair.key_name
    )

    connection = remote.ConnectionArgs(
        host=rsw_server.public_dns, 
        user="ubuntu", 
        private_key=Path("key.pem").read_text()
    )

    # Export final pulumi variables.
    pulumi.export('rsw_public_ip', rsw_server.public_ip)
    pulumi.export('rsw_public_dns', rsw_server.public_dns)
    pulumi.export('rsw_subnet_id', rsw_server.subnet_id)

    # --------------------------------------------------------------------------
    # Create FSX.
    # --------------------------------------------------------------------------
    fsx_file_system = fsx.LustreFileSystem(
        "fsx-lustre-file-system",
        storage_capacity=1200,
        subnet_ids=rsw_server.subnet_id,
        tags=TAGS | {"Name": f"{CONFIG_VALUES.email}-rsw-ha-fxs-lustre"}
    )

    # --------------------------------------------------------------------------
    # Install required software one each server
    # --------------------------------------------------------------------------
        
    command_set_environment_variables = remote.Command(
        "set environment variables", 
        create=pulumi.Output.concat(
            'echo "export RSW_LICENSE=', CONFIG_VALUES.rsw_license, '" > .env;',
        ), 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server])
    )

    command_install_justfile = remote.Command(
        f"install justfile",
        create="\n".join([
            """curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin;""",
            """echo 'export PATH="$PATH:$HOME/bin"' >> ~/.bashrc;"""
        ]),
        connection=connection,
        opts=pulumi.ResourceOptions(depends_on=[rsw_server])
    )

    command_copy_justfile = remote.CopyFile(
        f"copy ~/justfile",  
        local_path="server-side-justfile", 
        remote_path='justfile', 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server]),
        triggers=[hash_file("server-side-justfile")]
    )

    # --------------------------------------------------------------------------
    # Config files
    # --------------------------------------------------------------------------
    file_path_rserver = "config/rserver.conf"

    copy_rserver_conf = remote.Command(
        "copy ~/rserver.conf",
        create=pulumi.Output.concat(
            'echo "', 
            pulumi.Output.all(rsw_server.public_ip).apply(lambda x: create_template(file_path_rserver).render()), 
            '" > ~/rserver.conf'
        ),
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server]),
        triggers=[hash_file(file_path_rserver)]
    )
    
    file_path_launcher = "config/launcher.conf"

    copy_launcher_conf = remote.Command(
        "copy ~/launcher.conf",
        create=pulumi.Output.concat(
            'echo "', 
            pulumi.Output.all(rsw_server.public_ip).apply(lambda x: create_template(file_path_launcher).render()), 
            '" > ~/launcher.conf'
        ),
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server]),
        triggers=[hash_file(file_path_launcher)]
    )
    
    file_path_vscode = "config/vscode.extensions.conf"

    copy_vscode_conf = remote.Command(
        "copy ~/vscode.extensions.conf",
        create=pulumi.Output.concat(
            'echo "', 
            pulumi.Output.all(rsw_server.public_ip).apply(lambda x: create_template(file_path_vscode).render()), 
            '" > ~/vscode.extensions.conf'
        ),
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server]),
        triggers=[hash_file(file_path_vscode)]
    )

    # --------------------------------------------------------------------------
    # Build
    # --------------------------------------------------------------------------

    # command_build_rsw = remote.Command(
    #     f"build rsw", 
    #     create="""export PATH="$PATH:$HOME/bin"; just build-rsw""", 
    #     connection=connection, 
    #     opts=pulumi.ResourceOptions(depends_on=[command_copy_justfile])
    # )

main()
