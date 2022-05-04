import os
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple

import pulumi
from pulumi_aws import ec2
from pulumi_command import remote
from pulumi_tls import PrivateKey
from rich import inspect, print

from . import dstools
from . import linux

from .helpers import BaseConfig, dep


def make(config: BaseConfig):    
    # Stand up a server.
    server = ec2.Instance(
        "rstudio-package-manager",
        instance_type=config.ec2_size,
        vpc_security_group_ids=config.vpc_group_ids,
        ami=config.ami_id,
        tags=config.tags,
        key_name=config.key_pair.key_name
    )

    # Export final pulumi variables.
    pulumi.export('package_manager_public_ip', server.public_ip)
    pulumi.export('package_manager_public_dns', server.public_dns)
    
    # Create a connection to the server
    connection = remote.ConnectionArgs(
        host=server.public_dns, 
        user="ubuntu", 
        private_key=config.private_key
    )
    
    # --------------------------------------------------------------------------
    # Install prequisits.
    # --------------------------------------------------------------------------
    _sleep = remote.Command(
        "rspm-sleep", 
        create="sleep 5;", 
        connection=connection, 
        opts=dep([server])
    )

    _add_user = remote.Command(
        "rspm-add-user-sam", 
        create=linux.add_user_script("sam"), 
        connection=connection, 
        opts=dep([_sleep])
    )

    _apt_install = remote.Command(
        "rspm-apt-init", 
        create=install_prerequisites_script(), 
        connection=connection, 
        opts=dep([_add_user])
    )

    c_gdebi = remote.Command(
        "rspm-install-gdebi-core", 
        create=linux.install_gbebi_core_script(), 
        connection=connection, 
        opts=dep([_apt_install])
    )
    
    # --------------------------------------------------------------------------
    # Install and activate RSPM.
    # --------------------------------------------------------------------------
    c_install_r = remote.Command(
        "rspm-install-r-412", 
        create=dstools.install_r_script("4.1.2"), 
        connection=connection, 
        opts=dep([c_gdebi])
    )
    c_install_rspm = remote.Command(
        "rspm-install-package-manager", 
        create=install_script(os.getenv("RSPM_LICENSE")), 
        connection=connection, opts=dep([c_install_r])
    )
    c_set_admin = remote.Command(
        "rspm-set-admin", 
        create=set_admin_script("sam"), 
        connection=connection, 
        opts=dep([c_install_rspm])
    )
    c_restart = remote.Command(
        "rspm-restart", 
        create=restart_script(), 
        connection=connection,
        opts=dep([c_set_admin])
    )
    
    # --------------------------------------------------------------------------
    # Copy config files
    # --------------------------------------------------------------------------
    _c_conf_1 = remote.CopyFile(
        "rswpm-justfile", 
        local_path="templates/rspm/justfile", 
        remote_path="justfile", 
        connection=connection, 
        opts=dep([server])
    )

    # --------------------------------------------------------------------------
    # Serve repos.
    # --------------------------------------------------------------------------
    c_serve_cran = remote.Command(
        "rspm-serve-cran", 
        create=serve_cran_script(), 
        connection=connection, 
        opts=dep([c_restart])
    )

    _ = remote.Command(
        "rspm-serve-curated-cran", 
        create=serve_curated_cran_script(), 
        connection=connection, 
        opts=dep([c_serve_cran])
    )

    # _ = remote.Command(
    #     "rspm-serve-pypi", 
    #     create=serve_pypi_script(), 
    #     connection=connection, 
    #     opts=dep([c_restart])
    # )

    return server


def install_script(license_key: str) -> str:
    script = f"""
    curl -O https://cdn.rstudio.com/package-manager/ubuntu20/amd64/rstudio-pm_2021.12.0-3_amd64.deb
    sudo gdebi rstudio-pm_2021.12.0-3_amd64.deb -n
    sudo /opt/rstudio-pm/bin/license-manager activate {license_key}
    """
    return dedent(script).strip()


def restart_script() -> str:
    script = """
    sudo systemctl stop rstudio-pm
    sleep 5
    sudo systemctl start rstudio-pm
    sleep 5
    """
    return dedent(script).strip()


def create_template_dir_script() -> str:
    script = """
    mkdir ~/rstudio_templates
    """
    return dedent(script).strip()


def copy_config_files_script() -> str:
    script = """
    echo "Do nothing" 
    """
    return dedent(script).strip()


def set_admin_script(user: str) -> str:
    script = f"""
    sudo usermod -aG rstudio-pm {user}
    """
    return dedent(script).strip()


def serve_cran_script() -> str:
    """
    https://docs.rstudio.com/rspm/admin/getting-started/configuration/#quickstart-curated-cran
    """
    script = f"""
    sudo /opt/rstudio-pm/bin/rspm create repo --name=prod-cran --description='Access CRAN packages'
    sudo /opt/rstudio-pm/bin/rspm subscribe --repo=prod-cran --source=cran
    sudo /opt/rstudio-pm/bin/rspm sync --type=cran
    """
    return dedent(script).strip()


def serve_curated_cran_script() -> str:
    """
    https://docs.rstudio.com/rspm/admin/getting-started/configuration/#quickstart-cran
    """
    script = f"""
    sudo /opt/rstudio-pm/bin/rspm sync --type=cran
    sudo /opt/rstudio-pm/bin/rspm create source --name=subset --type=curated-cran --snapshot=2020-07-06
    sudo /opt/rstudio-pm/bin/rspm add --packages=ggplot2,shiny --source=subset
    sudo /opt/rstudio-pm/bin/rspm add --packages=ggplot2,shiny --source=subset --snapshot=2020-07-06 --commit
    sudo /opt/rstudio-pm/bin/rspm update --source=subset --snapshot=2020-10-07
    sudo /opt/rstudio-pm/bin/rspm update --source=subset --snapshot=2020-10-07 --commit
    sudo /opt/rstudio-pm/bin/rspm create repo --name=curated-cran --description='Access curated CRAN packages by date'
    sudo /opt/rstudio-pm/bin/rspm subscribe --repo=curated-cran --source=subset
    """
    return dedent(script).strip()


def serve_pypi_script() -> str:
    """
    https://docs.rstudio.com/rspm/admin/getting-started/configuration/#quickstart-pypi-packages
    """
    script = f"""   
    sudo /opt/rstudio-pm/bin/rspm create repo --name=pypi --type=python --description='Access PyPI packages'
    sudo /opt/rstudio-pm/bin/rspm subscribe --repo=pypi --source=pypi
    sudo /opt/rstudio-pm/bin/rspm sync --type=pypi
    """
    return dedent(script).strip()


def install_prerequisites_script() -> str:
    """
    https://docs.rstudio.com/rspm/admin/getting-started/configuration/#quickstart-pypi-packages
    """
    script = f"""   
    sudo apt-get update; 
    # Install helpful unix tools
    sudo apt-get -y install tree bat;
    echo "alias bat='batcat --paging never'" >> ~/.bashrc
    # Install just
    curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin;
    echo 'export PATH="$PATH:$HOME/bin"' >> ~/.bashrc;
    """
    return dedent(script).strip()


