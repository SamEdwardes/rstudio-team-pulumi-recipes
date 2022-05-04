from textwrap import dedent


def install_docker_script() -> str:
    script = f"""
    sudo apt-get update
    sudo apt-get install ca-certificates curl gnupg lsb-releas
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install docker-ce docker-ce-cli containerd.io
    """
    return dedent(script).strip()
   

def install_ldap_script() -> str:
    script = f"""
    sudo apt-get instal openldap*
    sudo systemctl start slapd
    sudo systemctl enable slapd
    sudo slap
    """
    return dedent(script).strip()