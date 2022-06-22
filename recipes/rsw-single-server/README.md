# RStudio Workbench High availability setup.

![](infra.drawio.png)

⚠️ This deployment uses a self signed cert. It will not open in Google Chrome. It will open in FireFox after you accept the security warnings.

## Usage

There are two primary files:

- `__main__.py`: contains the python code that will stand up the AWS resources.
- `server-side-justfile`: contains the commands required to install RSW and the required dependencies. This file will be copied to each ec2 instance so that it can be executed on the server.

### Step 1: Create new virtual environment

```bash
python -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip wheel
pip install -r requirements.txt
```

### Step 2: Pulumi configuration

Select your pulumi stack.

```bash
pulumi stack select dev
```

Set the following pulumi configuration values:

```bash
pulumi config set email <XXXX>                 # Will be assigned to `rs:owner` tag in AWS
pulumi config set name <XXXX>                  # Will be used with the `Name` tag in AWS to easily identify your resources
pulumi config set aws_private_key_path <XXXX>  # The location of your aws private key, for example /Users/sam/sam-aws-key.pem
pulumi config set aws_ssh_key_id <XXXX>        # The ID if your SSH - can be founds in the AWS UI
pulumi config set --secret rsw_license <XXXX>
pulumi config set daily false                  # Should be `true` or `false`. If `true` will use the daily build.
```

### Step 3: Spin up infra

Create all of the infrastructure.

```bash
pulumi up
```

### Step 3: Validate that RSW is working

Visit RSW in your browser (use FireFox instead of Chrome):

```
just open
```

Login and start some new sessions.

You can also ssh into the ec2 instances for any debugging.

```bash
just ssh
```
