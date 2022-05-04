"""
Scripts related to insalling and managing nginx.
"""

from textwrap import dedent

def install_script() -> str:
    """
    https://docs.rstudio.com/ide/server-pro/access_and_security/running_with_a_proxy.html#nginx-configuration
    """
    script = """
    sudo apt-get install -y nginx;
    sudo systemctl restart nginx;
    """
    return dedent(script).strip()


def restart_script() -> str:
    script = """
    sudo systemctl restart nginx;
    """
    return dedent(script).strip()


def create_template_dir_script() -> str:
    script = """
    mkdir ~/rstudio_templates;
    """
    return dedent(script).strip()


def copy_config_script() -> str:
    script = """
    sudo cp rstudio_templates/index.html /usr/share/nginx/html/index.html;
    sudo cp rstudio_templates/nginx.conf /etc/nginx/nginx.conf;
    """
    return dedent(script).strip()


def ssl_cert_script() -> str:
    """
    https://vexxhost.com/resources/tutorials/how-to-create-a-ssl-certificate-on-nginx-for-ubuntu/
    """
    script = """
    sudo mkdir /etc/nginx/ssl;
    cd /etc/nginx/ssl;
    sudo openssl genrsa -des3 -out server.key 1024;
    sudo openssl req -new -key server.key -out server.csr;
    sudo cp server.key server.key.org;
    sudo openssl rsa -in server.key.org -out server.key;
    sudo openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt;
    sudo service nginx restart;
    """
    return dedent(script).strip()
