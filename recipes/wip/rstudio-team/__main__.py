import os
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple

import pulumi
from pulumi_aws import ec2, s3
from pulumi_command import remote
from pulumi_tls import PrivateKey
from rich import inspect, print

from src.helpers import BaseConfig, decode_key, dep
from src import dstools
from src import nginx
from src import rsc
from src import rspm
from src import rsw
from src import linux


def make_server(
    name: str, 
    tags: Dict, 
    key_pair: ec2.KeyPair, 
    vpc_group_ids: List[str]
):
    server = ec2.Instance(
        name,
        instance_type="t3.small",
        vpc_security_group_ids=vpc_group_ids,
        ami="ami-0fb653ca2d3203ac1",  # Ubuntu Server 20.04 LTS (HVM), SSD Volume Type
        tags=tags,
        key_name=key_pair.key_name
    )
    
    # Export final pulumi variables.
    pulumi.export(f'{name}-public-ip', server.public_ip)
    pulumi.export(f'{name}-public-dns', server.public_dns)

    return server

    
def make_rstudio_workbench(config: BaseConfig):    
    # Stand up a server.
    server = ec2.Instance(
        "rstudio-workbench",
        instance_type=config.ec2_size,
        vpc_security_group_ids=config.vpc_group_ids,
        ami=config.ami_id,
        tags=config.tags,
        key_name=config.key_pair.key_name
    )
    
    # Export final pulumi variables.
    pulumi.export('workbench_public_ip', server.public_ip)
    pulumi.export('workbench_public_dns', server.public_dns)

    # Set up a connection
    connection = remote.ConnectionArgs(
        host=server.public_dns, 
        user="ubuntu", 
        private_key=config.private_key
    )
    # Execute all the commands on EC2 instance.
    # --------------------------------------------------------------------------
    # Add users.
    # --------------------------------------------------------------------------
    
    _sleep = remote.Command("rsw-sleep", create="sleep 5;", connection=connection, opts=dep([server]))
    _ = remote.Command("rsw-add-user-sam", create=linux.add_user_script("sam"), connection=connection, opts=dep([_sleep]))
    _ = remote.Command("rsw-add-user-jake", create=linux.add_user_script("jake"), connection=connection, opts=dep([_sleep]))
    _ = remote.Command("rsw-add-user-olivia", create=linux.add_user_script("olivia"), connection=connection, opts=dep([_sleep]))

    # --------------------------------------------------------------------------
    # Install prequisits.
    # --------------------------------------------------------------------------
    _apt_init = remote.Command(
        "rsw-apt-init", 
        create=dedent("""
        sudo apt-get update; 
        sudo apt-get install -y tree bat;
        echo "alias bat='batcat --paging never'" >> ~/.bashrc;

        """).strip(), 
        connection=connection, 
        opts=dep([_sleep])
    )
    _c_gdebi = remote.Command("rsw-install-gdebi", create=linux.install_gbebi_core_script(), connection=connection, opts=dep([_apt_init]))
    _c_r_412 = remote.Command("rsw-install-r-4.1.2", create=dstools.install_r_script(r_version="4.1.2", symlink=True), connection=connection, opts=dep([_c_gdebi]))
    _c_r_405 = remote.Command("rsw-install-r-4.0.5", create=dstools.install_r_script(r_version="4.0.5"), connection=connection, opts=dep([_c_r_412]))
    _c_miniconda = remote.Command("rsw-install-miniconda", create=dstools.install_miniconda_script(), connection=connection, opts=dep([server]))
    _install_python = remote.Command("rsw-install-python", create=dstools.install_python_script(python_version="3.9.7"), connection=connection, opts=dep([_c_miniconda]))

    # --------------------------------------------------------------------------
    # Install and activate RSW.
    # --------------------------------------------------------------------------
    _c_install_rsw = remote.Command(
        "rsw-install-workbench", 
        create=rsw.install_script(), 
        connection=connection, 
        opts=dep([_c_r_412, _c_r_405, _install_python])
    )

    _c_rsw_license = remote.Command(
        "rsw-activate-workbench-license", 
        create=rsw.activate_license_script(os.getenv("RSW_LICENSE")), 
        connection=connection, 
        opts=dep([_c_install_rsw])
    )

    _ = remote.Command(
        "rsw-install-vscode", 
        create=rsw.install_vscode_script(), 
        connection=connection, 
        opts=dep([_c_rsw_license])
    )

    # --------------------------------------------------------------------------
    # Copy config files.
    # --------------------------------------------------------------------------
    _copy_justfile = remote.CopyFile(
        "copy-rsw-justfile", 
        local_path="templates/rsw/justfile", 
        remote_path="justfile", 
        connection=connection, 
        opts=dep([server])
    )
    _c_conf_1 = remote.CopyFile(
        "rsw-rserver-conf", 
        local_path="templates/rsw/rserver.conf", 
        remote_path="~/rserver.conf", 
        connection=connection, 
        opts=dep([server])
    )
    _c_conf_2 = remote.CopyFile(
        "rsw-launcher-conf", 
        local_path="templates/rsw/launcher.conf", 
        remote_path="~/launcher.conf", 
        connection=connection, 
        opts=dep([server])
        )
    _c_conf_3 = remote.CopyFile(
        "rsw-jupyter-conf", 
        local_path="templates/rsw/jupyter.conf", 
        remote_path="~/jupyter.conf", 
        connection=connection, 
        opts=dep([server])
    )
    _c_conf_4 = remote.CopyFile(
        "rsw-ression-profile", 
        local_path="templates/rsw/rsession-profile", 
        remote_path="~/rsession-profile", 
        connection=connection, 
        opts=dep([server])
    )
    _mv_config = remote.Command(
        "rsw-move-config-files", 
        create=dedent("""
            sudo cp ~/rserver.conf /etc/rstudio/rserver.conf;
            sudo cp ~/launcher.conf /etc/rstudio/launcher.conf;
            sudo cp ~/jupyter.conf /etc/rstudio/jupyter.conf;
            sudo cp ~/rsession-profile /etc/rstudio/rsession-profile;
        """).strip(), 
        connection=connection, 
        opts=dep([_c_conf_1, _c_conf_2, _c_conf_3, _c_conf_4])
    )
    _ = remote.Command(
        "rsw-restart", 
        create=rsw.restart_script(), 
        connection=connection, 
        opts=dep([_mv_config])
    )
    
    return server


def make_rstudio_connect(config: BaseConfig):
    config.tags["Name"] = "samedwardes-rstudio-connect"
    
    # Stand up a server.
    server = ec2.Instance(
        "rstudio-connect",
        instance_type=config.ec2_size,
        vpc_security_group_ids=config.vpc_group_ids,
        ami=config.ami_id,
        tags=config.tags,
        key_name=config.key_pair.key_name
    )

    # Export final pulumi variables.
    pulumi.export('connect_public_ip', server.public_ip)
    pulumi.export('connect_public_dns', server.public_dns)
    
    # Connect to the Ec2 instance.        
    connection = remote.ConnectionArgs(
        host=server.public_dns, 
        user="ubuntu", 
        private_key=config.private_key
    )

    # --------------------------------------------------------------------------
    # Install prequisits.
    # --------------------------------------------------------------------------
    _apt_init = remote.Command(
        "rsc-apt-init", 
        create=dedent("""
        sudo apt-get update; 
        sudo apt-get install -y tree bat;
        echo "alias bat='batcat --paging never'" >> ~/.bashrc;
        """).strip(), 
        connection=connection, 
        opts=dep([server])
    )
    _c_gdebi = remote.Command("rsc-install-gdebi-core", create=linux.install_gbebi_core_script(), connection=connection, opts=dep([_apt_init]))
    _c_r_412 = remote.Command("rsc-install-r-4.1.2", create=dstools.install_r_script("4.1.2", symlink=True), connection=connection, opts=dep([_c_gdebi]))
    _ = remote.Command("rsc-install-r-4.0.5", create=dstools.install_r_script("4.0.5"), connection=connection, opts=dep([_c_r_412]))
    _c_miniconda = remote.Command("rsc-install-miniconda", create=dstools.install_miniconda_script(), connection=connection, opts=dep([server]))
    _ = remote.Command("rsc-install-python", create=dstools.install_python_script("3.9.7"), connection=connection, opts=dep([_c_miniconda]))
    
    # --------------------------------------------------------------------------
    # Install and activate RSC.
    # --------------------------------------------------------------------------
    _c_rsc = remote.Command(
        "rsc-install-connect", 
        create=rsc.install_script(os.getenv("RSC_LICENSE")), 
        connection=connection, 
        opts=dep([_c_r_412])
    )
    
    # --------------------------------------------------------------------------
    # Copy config files.
    # --------------------------------------------------------------------------
    _copy_justfile = remote.CopyFile(
        "copy-rsc-justfile", 
        local_path="templates/rsc/justfile", 
        remote_path="justfile", 
        connection=connection, 
        opts=dep([server])
    )
    _c_config = remote.CopyFile(
        "rsc-copy-config",
        local_path="templates/rsc/rstudio-connect.gcfg",
        remote_path="rstudio-connect.gcfg", 
        connection=connection, 
        opts=dep([_c_r_412])
    )
    _mv_config = remote.Command(
        "rsc-mv-config", 
        create=dedent("""
        sudo mv ~/rstudio-connect.gcfg /etc/rstudio-connect/rstudio-connect.gcfg
        """).strip(),
        connection=connection, 
        opts=dep([_c_config, _c_rsc])
    )
    
    _ = remote.Command("rsc-restart", create=rsc.restart_script(), connection=connection, opts=dep([_mv_config]))

    return server


def make_security_group(resource_id: str, port: int, description: str, landing_page_ip, config: BaseConfig):
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
            {"protocol": "TCP", "from_port": port, "to_port": port, 'cidr_blocks': [landing_page_ip.apply(lambda x: f"{x}/32")], "description": description},
        ],
        egress=[
            {"protocol": "All", "from_port": -1, "to_port": -1, 'cidr_blocks': ['0.0.0.0/0'], "description": "Allow all outbout traffic"},
        ],
        tags=config.tags
    )
    return sg


def get_key_pair(config: pulumi.Config) -> ec2.KeyPair:
    key_name = config.get('keyName')
    public_key = config.get('publicKey')
    if key_name is None:
        return ec2.KeyPair('key', public_key=public_key)


def main():    
    # Set up keys.
    config = pulumi.Config()
    key_pair = get_key_pair(config)
    private_key = config.require_secret('privateKey').apply(decode_key)

    # --------------------------------------------------------------------------
    # Landing page
    # --------------------------------------------------------------------------
    landing_page_stack = pulumi.StackReference("SamEdwardes/landing-page/dev")
    landing_page_ip = landing_page_stack.get_output("eip_public_ip")

    # --------------------------------------------------------------------------
    # RSPM
    # --------------------------------------------------------------------------
    rspm_sg_config = BaseConfig()
    rspm_sg_config.tags["name"] = "samedwardes-sg-rspm"
    rspm_sg = make_security_group(
        "rspm-security-group", 
        port=4242, 
        description="RSPM", 
        landing_page_ip=landing_page_ip, 
        config=rspm_sg_config
    )
    
    rspm_config = BaseConfig(key_pair=key_pair, private_key=private_key, vpc_group_ids=[rspm_sg.id])
    rspm_config.tags["Name"] = "samedwardes-rstudio-package-manager"
    rspm.make(rspm_config)

    # --------------------------------------------------------------------------
    # RSW
    # --------------------------------------------------------------------------
    rsw_sg_config = BaseConfig()
    rsw_sg_config.tags["name"] = "samedwardes-sg-rsw"
    rsw_sg = make_security_group(
        "samedwardes-sg-rsw", 
        port=8787, 
        description="RSW", 
        landing_page_ip=landing_page_ip, 
        config=rsw_sg_config
    )
    
    rsw_config = BaseConfig(key_pair=key_pair, private_key=private_key, vpc_group_ids=[rsw_sg.id])
    rsw_config.tags["Name"] = "samedwardes-rstudio-workbench"
    rsw_server = make_rstudio_workbench(rsw_config)
    
    # --------------------------------------------------------------------------
    # RSC
    # --------------------------------------------------------------------------
    rsc_sg_config = BaseConfig()
    rsc_sg_config.tags["name"] = "samedwardes-sg-rsc"
    rsc_sg = make_security_group("samedwardes-sg-rsc", port=3939, description="RSC", landing_page_ip=landing_page_ip, config=rsc_sg_config)
    
    rsc_config = BaseConfig(key_pair=key_pair, private_key=private_key, vpc_group_ids=[rsc_sg.id])
    rsc_config.tags["Name"] = "samedwardes-rstudio-connect"
    rsc_server = make_rstudio_connect(rsc_config)


main()
