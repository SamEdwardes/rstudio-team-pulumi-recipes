from textwrap import dedent

def install_script() -> str:
    script = f"""
    curl -O https://download2.rstudio.org/server/bionic/amd64/rstudio-workbench-2022.02.0-443.pro2-amd64.deb;
    sudo gdebi rstudio-workbench-2022.02.0-443.pro2-amd64.deb -n;
    """
    return dedent(script).strip()


def activate_license_script(rsw_license: str) -> str:
    script = f"""
    sudo rstudio-server license-manager activate {rsw_license}
    """
    return dedent(script).strip()


def create_template_dir_script() -> str:
    script = """
    mkdir ~/rstudio_templates
    """
    return dedent(script).strip()


def move_config_files_script() -> str:
    script = """
    sudo cp ~/rstudio_templates/rserver.conf /etc/rstudio/rserver.conf;
    sudo cp ~/rstudio_templates/launcher.conf /etc/rstudio/launcher.conf;
    sudo cp ~/rstudio_templates/jupyter.conf /etc/rstudio/jupyter.conf;
    sudo cp ~/rstudio_templates/rsession-profile /etc/rstudio/rsession-profile;
    """
    return dedent(script).strip()


def restart_script() -> str:
    script = """
    sudo rstudio-server restart;
    sleep 5;
    sudo rstudio-launcher restart;
    sleep 5;
    """
    return dedent(script).strip()


def install_vscode_script() -> str:
    script = """
    sudo rstudio-server install-vs-code /opt/code-server;
    sudo rstudio-server restart;
    sudo rstudio-server install-vs-code-ext -d /opt/code-server;
    """
    return dedent(script).strip()




