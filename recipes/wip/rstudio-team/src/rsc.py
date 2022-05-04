from textwrap import dedent

def install_script(connect_license: str) -> str:
    """
    https://docs.rstudio.com/rsc/manual-install/
    """
    script = f"""
    curl -O https://cdn.rstudio.com/connect/2022.02/rstudio-connect_2022.02.3~ubuntu20_amd64.deb
    sudo gdebi rstudio-connect_2022.02.3~ubuntu20_amd64.deb -n
    # Check the status using:
    # sudo systemctl status rstudio-connect
    
    # Activate license
    sudo /opt/rstudio-connect/bin/license-manager activate {connect_license}
    
    # Install system dependencies
    sudo apt install -y perl make libpng-dev tcl tk tk-dev tk-table default-jdk \
        imagemagick libmagick++-dev gsfonts libxml2-dev git libssl-dev \
        libcurl4-openssl-dev libjpeg-dev zlib1g-dev unixodbc-dev libfreetype6-dev \
        libfribidi-dev libharfbuzz-dev libsodium-dev libglu1-mesa-dev \
        libgl1-mesa-dev libssh2-1-dev libicu-dev libmysqlclient-dev libgeos-dev \
        libgdal-dev gdal-bin libproj-dev libcairo2-dev libglpk-dev libgmp3-dev \
        cmake python3 libv8-dev libudunits2-dev libfontconfig1-dev libtiff-dev
    
    # Install requirements for Python APIs and interactive appplications
    sudo apt install -y libev-dev 
    """
    return dedent(script).strip()


def restart_script() -> str:
    script = """
    sudo systemctl restart rstudio-connect
    sleep 5
    """
    return dedent(script).strip()
