from pathlib import Path
from dataclasses import dataclass, field

import pulumi
from pulumi_aws import ec2
from pulumi_command import remote
import pulumi_tls as tls
import requests
from rich import print

# Setup pulumi configuration
config = pulumi.Config()

@dataclass 
class ConfigValues:
    name: str = field(default_factory=lambda: config.require("name"))
    email: str = field(default_factory=lambda: config.require("email"))
    aws_private_key_path: str = field(default_factory=lambda: config.require("aws_private_key_path"))
    aws_ssh_key_id: str = field(default_factory=lambda: config.require("aws_ssh_key_id"))
    rsw_license: str = field(default_factory=lambda: config.require("rsw_license"))
    daily: bool = field(default_factory=lambda: config.require("daily").lower() in ("yes", "true", "t", "1"))


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


def get_latest_build() -> str:
    url = "https://dailies.rstudio.com/rstudio/latest/index.json"
    r = requests.get(url)
    data = r.json()
    link = data["products"]["workbench"]["platforms"]["bionic"]["link"]
    filename = data["products"]["workbench"]["platforms"]["bionic"]["filename"]
    return (link, filename)

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
    # Create a self signed cert
    # --------------------------------------------------------------------------
    # Create a new private CA
    ca_private_key = tls.PrivateKey("ca-private-key",
        algorithm="ECDSA",
        ecdsa_curve="P384"
    )

    # Create a self signed cert
    ca_cert = tls.SelfSignedCert(
        "ca-self-signed-cert",
        private_key_pem=ca_private_key.private_key_pem,
        is_ca_certificate=True,
        validity_period_hours=8760,
        allowed_uses=[
            "key_encipherment",
            "digital_signature",
            "cert_signing"
        ],
        dns_names=[rsw_server.public_dns],
        subject=tls.SelfSignedCertSubjectArgs(
            common_name="private-ca",
            organization="RStudio"
        )
    )

    # --------------------------------------------------------------------------
    # Install required software one each server
    # --------------------------------------------------------------------------
    connection = remote.ConnectionArgs(
        host=rsw_server.public_dns, 
        user="ubuntu", 
        private_key=private_key
    )

    if CONFIG_VALUES.daily:
        rsw_url, rsw_filename = get_latest_build()
    else:
        rsw_url = "https://download2.rstudio.org/server/bionic/amd64/rstudio-workbench-2022.02.3-492.pro3-amd64.deb"
        rsw_filename = "rstudio-workbench-2022.02.3-492.pro3-amd64.deb"

    tls_crt_setup = remote.Command(
        "server-set-tls-crt",
        create=pulumi.Output.concat(
            '''sudo echo "''',
            ca_cert.cert_pem,
            '''" > ~/server.crt'''
        ),
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server, ca_cert, ca_private_key])
    )
    
    tls_key_setup = remote.Command(
        "server-set-tls-key",
        create=pulumi.Output.concat(
            '''sudo echo "''',
            ca_private_key.private_key_pem,
            '''" > ~/server.key'''
        ),
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server, ca_cert, ca_private_key])
    )

    command_set_env = remote.Command(
        "server-set-env", 
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
            
            f'''echo "export RSW_URL=''', 
            rsw_url,
            '''" >> .env;''',
            
            f'''echo "export RSW_FILENAME=''', 
            rsw_filename,
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
        f"server-copy-justfile-",  
        local_path="server-side-justfile", 
        remote_path='justfile', 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server])
    )

    # command_build_rsw = remote.Command(
    #     f"server-build-rsw", 
    #     create="""export PATH="$PATH:$HOME/bin"; just build-rsw""", 
    #     connection=connection, 
    #     opts=pulumi.ResourceOptions(depends_on=[command_copy_justfile])
    # )

main()