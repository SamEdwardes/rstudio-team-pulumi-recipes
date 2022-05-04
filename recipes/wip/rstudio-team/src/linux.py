from textwrap import dedent


def apt_repo_init_script() -> str:
    script = """
    sudo add-apt-repository main;
    sudo add-apt-repository universe;
    sudo apt-get update;
    sleep 10;
    """
    return dedent(script).strip()


def apt_get_update_script() -> str:
    script = """
    sudo apt-get update;
    """
    return dedent(script).strip()


def apt_get_install_script(library: str) -> str:
    script = f"""
    sudo apt-get install -y {library};
    """
    return dedent(script).strip()    


def apt_get_init_script() -> str:
    """
    Update apt and install some of the basic tools I want on every server.
    """
    script = """
    sudo add-apt-repository main;
    sudo add-apt-repository universe;
    sudo apt-get update;
    sudo apt-get install -y tree;
    sudo apt install -y bat;
    mkdir -p ~/.local/bin;
    ln -s /usr/bin/batcat ~/.local/bin/bat;
    """
    return dedent(script).strip()


def install_gbebi_core_script() -> str:
    script = """
    sudo add-apt-repository main;
    sudo add-apt-repository universe;
    sudo apt-get update;
    sudo apt-get install -y gdebi-core;
    """
    return dedent(script).strip()


def add_user_script(user_name: str, password: str = "password") -> str:
    script = f"""
    sudo useradd -m -s /bin/bash {user_name};
    echo -e '{password}\n{password}' | sudo passwd {user_name};
    """
    return dedent(script).strip()




