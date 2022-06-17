from pathlib import Path
from dataclasses import dataclass, field

import pulumi
from pulumi_aws import ec2
from pulumi_command import remote

# Setup pulumi configuration
config = pulumi.Config()

@dataclass 
class ConfigValues:
    name: str = field(default_factory=lambda: config.require("name"))
    email: str = field(default_factory=lambda: config.require("email"))
    aws_private_key_path: str = field(default_factory=lambda: config.require("aws_private_key_path"))
    aws_ssh_key_id: str = field(default_factory=lambda: config.require("aws_ssh_key_id"))
    rsw_license: str = field(default_factory=lambda: config.require("rsw_license"))


CONFIG_VALUES = ConfigValues()
TAGS = {
    "rs:environment": "development",
    "rs:owner": CONFIG_VALUES.email,
    "rs:project": "solutions",
}


def get_private_key(file_path: str) -> str:
    path = Path(file_path)
    if path.exists() == False:
        path = path.expanduser()
    with open(path, mode="r") as f:
        private_key = f.read()
    return private_key


def main():
    # --------------------------------------------------------------------------
    # Set up keys.
    # --------------------------------------------------------------------------
    key_pair = ec2.get_key_pair(key_pair_id=CONFIG_VALUES.aws_ssh_key_id)
    private_key = get_private_key(CONFIG_VALUES.aws_private_key_path)

    # --------------------------------------------------------------------------
    # Make security groups
    # --------------------------------------------------------------------------
    security_group = ec2.SecurityGroup(
        "rsw-security-group",
        description= CONFIG_VALUES.name + " security group for Pulumi deployment",
        ingress=[
            {"protocol": "TCP", "from_port": 22, "to_port": 22, 'cidr_blocks': ['0.0.0.0/0'], "description": "SSH"},
            {"protocol": "TCP", "from_port": 8787, "to_port": 8787, 'cidr_blocks': ['0.0.0.0/0'], "description": "RSW"},
            {"protocol": "TCP", "from_port": 443, "to_port": 443, 'cidr_blocks': ['0.0.0.0/0'], "description": "HTTPS"},
            {"protocol": "TCP", "from_port": 80, "to_port": 80, 'cidr_blocks': ['0.0.0.0/0'], "description": "HTTP"},
        ],
        egress=[
            {"protocol": "All", "from_port": -1, "to_port": -1, 'cidr_blocks': ['0.0.0.0/0'], "description": "Allow all outbound traffic"},
        ],
        tags=TAGS
    )

    # --------------------------------------------------------------------------
    # Stand up the servers
    # --------------------------------------------------------------------------
    # Ubuntu Server 20.04 LTS (HVM), SSD Volume Type for us-east-2
    ami_id = "ami-0fb653ca2d3203ac1"

    rsw_server = ec2.Instance(
        f"rstudio-workbench-server",
        instance_type="t3.medium",
        vpc_security_group_ids=[security_group.id],
        ami=ami_id,                 
        tags=TAGS | {"Name": f"{CONFIG_VALUES.name}-rsw-server"},
        key_name=key_pair.key_name
    )

    # Export final pulumi variables.
    pulumi.export(f'rsw_public_ip', rsw_server.public_ip)
    pulumi.export(f'rsw_public_dns', rsw_server.public_dns)
    pulumi.export(f'rsw_subnet_id', rsw_server.subnet_id)
  
    # --------------------------------------------------------------------------
    # Install required software one each server
    # --------------------------------------------------------------------------
    connection = remote.ConnectionArgs(
        host=rsw_server.public_dns, 
        user="ubuntu", 
        private_key=private_key
    )

    command_set_env = remote.Command(
        f"server-set-env", 
        create=pulumi.Output.concat(
            f'''echo "export SERVER_IP_ADDRESS=''', 
            rsw_server.public_ip,
            '''" > .env;\n''',
            
            f'''echo "export SERVER_PUBLIC_DNS=''', 
            rsw_server.public_dns,
            '''" >> .env;\n''',

            f'''echo "export RSW_LICENSE=''', 
            CONFIG_VALUES.rsw_license,
            '''" >> .env;''',
        ), 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server])
    )

    command_install_justfile = remote.Command(
        f"server-install-justfile",
        create="\n".join([
            """curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin;""",
            """echo 'export PATH="$PATH:$HOME/bin"' >> ~/.bashrc;"""
        ]),
        connection=connection,
        opts=pulumi.ResourceOptions(depends_on=[rsw_server])
    )

    command_copy_justfile = remote.CopyFile(
        f"server-copy-justfile",  
        local_path="server-side-justfile", 
        remote_path='justfile', 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server])
    )

    command_build_rsw = remote.Command(
        f"server-build-rsw", 
        create="""export PATH="$PATH:$HOME/bin"; just build-rsw""", 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[command_copy_justfile])
    )

main()