from textwrap import dedent


def install_r_script(r_version = "4.1.2", symlink=False) -> str:
    script = f"""
    curl -O https://cdn.rstudio.com/r/ubuntu-2004/pkgs/r-{r_version}_1_amd64.deb
    sudo gdebi r-{r_version}_1_amd64.deb -n
    """
    symlink_script = f"""
    sudo ln -s /opt/R/{r_version}/bin/R /usr/local/bin/R
    sudo ln -s /opt/R/{r_version}/bin/Rscript /usr/local/bin/Rscript
    """
    if symlink:
        return "\n".join([dedent(script).strip(), dedent(symlink_script).strip()])
    return dedent(script).strip()


def install_miniconda_script() -> str:
    script = f"""
    sudo mkdir /opt/python
    sudo curl -fsSL -o /opt/python/miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    sudo chmod 755 /opt/python/miniconda.sh
    sudo /opt/python/miniconda.sh -b -p /opt/python/miniconda
    """
    return dedent(script).strip()


def install_python_script(python_version: str = "3.9.7") -> str:
    script = f"""
    # Install specific version of python
    sudo /opt/python/miniconda/bin/conda create --quiet --yes \
        --prefix /opt/python/"{python_version}" \
        --channel conda-forge \
        python="{python_version}"

    # Upgrade required python tools
    /opt/python/"{python_version}"/bin/pip install --upgrade \
        pip setuptools wheel
        
    sudo /opt/python/"{python_version}"/bin/pip install virtualenv

    # Make python available as a jupyter kernel
    sudo /opt/python/{python_version}/bin/pip install ipykernel
    sudo /opt/python/{python_version}/bin/python -m ipykernel install --name py{python_version} --display-name "Python {python_version}"

    # Install jupyter stuff.
    # https://docs.rstudio.com/rsw/integration/jupyter-standalone/#4-install-jupyter-notebooks-jupyterlab-and-python-packages
    sudo /opt/python/{python_version}/bin/pip install jupyter jupyterlab rsp_jupyter rsconnect_jupyter

    sudo /opt/python/{python_version}/bin/jupyter-nbextension install --sys-prefix --py rsp_jupyter
    sudo /opt/python/{python_version}/bin/jupyter-nbextension enable --sys-prefix --py rsp_jupyter
    sudo /opt/python/{python_version}/bin/jupyter-nbextension install --sys-prefix --py rsconnect_jupyter
    sudo /opt/python/{python_version}/bin/jupyter-nbextension enable --sys-prefix --py rsconnect_jupyter
    sudo /opt/python/{python_version}/bin/jupyter-serverextension enable --sys-prefix --py rsconnect_jupyter

    # sudo /opt/python/{python_version}/bin/pip install altair beautifulsoup4 \
    #   cloudpickle cython dask gensim keras matplotlib nltk numpy pandas pillow \
    #   pyarrow requests scipy scikit-image scikit-learn scrapy seaborn spacy \
    #   sqlalchemy statsmodels tensorflow xgboost
    """
    return dedent(script).strip()