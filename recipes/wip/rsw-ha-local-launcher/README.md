# RStudio Workbench High availability setup.

## Usage

### Step 1: create ssh key

Next, generate an OpenSSH keypair for use with your server - as per the AWS [Requirements][1]

```bash
ssh-keygen -t rsa -f rsa -b 4096 -m PEM
cat rsa.pub | pulumi config set publicKey --
cat rsa | pulumi config set privateKey --secret --
pulumi config set aws:region ca-central-1
```

### Step 2: spin up base infrastructure

Spin up all of the required infrastructure including:

- 2 EC2 instances with RSW installed.
- 1 EFS.
- 1 Postgresql database.

Run the following command:

```bash
pulumi up
```

### Step 3: Mount the EFS drive to the EC2 instances

Each ec2 instance should have the EFS drive mounted to it. RStudio reccommends using the `efs-utils` command from Amazon. Run the following commands on each instance.

```bash
sudo apt-get -y install binutils;
git clone https://github.com/aws/efs-utils;
cd efs-utils;
./build-deb.sh;
sudo apt-get -y install ./build/amazon-efs-utils*deb;
cd ~;
```

Then mount the EFS instance with the following commands:

```bash
sudo mkdir -p /mnt/efs;
sudo mount -t efs -o tls fs-0ae474bb0403fc7c6:/ /mnt/efs;
```

Create a directory for shared storage (only run on first server):

```bash
sudo mkdir -p /mnt/efs/rstudio-server/shared-storage
```

> ⚠️ remember to replace `fs-0c4a7687b8838df0d` with the correct id.

### Step 4: Create users with home directories in EFS

Create the users on the first server.

```bash
export TMP_USERNAME=allie
sudo useradd --create-home --home-dir /mnt/efs/$TMP_USERNAME -s /bin/bash $TMP_USERNAME;
echo -e 'password\npassword' | sudo passwd $TMP_USERNAME;
```

On all other servers run the same command, but do not create the home directory again.

```bash
export TMP_USERNAME=kelly
sudo useradd --no-create-home --home-dir /mnt/efs/$TMP_USERNAME -s /bin/bash $TMP_USERNAME;
echo -e 'password\npassword' | sudo passwd $TMP_USERNAME;
```

### Step 5: Update config files

#### `/etc/rstudio/rserver.conf`

For each server add the folling options in the config file.

```ini
# /etc/rstudio/rserver.conf

admin-enabled=1
admin-group=sam
server-shared-storage-path=/mnt/efs/rstudio-server/shared-storage
secure-cookie-key-file=/mnt/efs/rstudio-server/secure-cookie-key
```

#### `/etc/rstudio/load-balancer`

For each server add the folling options in the config file. Note that the `www-host-name` should be the IP address for the server that the file lives on (e.g. it will be different on each server).

```ini
# /etc/rstudio/load-balancer

balancer=sessions
www-host-name=3.96.47.5:8787
```

#### `/etc/rstudio/database.conf`

For each server add the following file. Note that the host can be obtained from endpoint of the database in the AWS console.

```ini
# /etc/rstudio/database.conf

# Note: when connecting to a PostgreSQL database, a default empty rstudio database must first be created!
provider=postgresql

# Specifies the host (hostname or IP address) of the database host
host=rsw-db1c99374.clsoguffisld.ca-central-1.rds.amazonaws.com

# Specifies the database to connect to
database=rsw_data

# Specifies the TCP port where the database is listening for connections
port=5432

# Specifies the database connection username
username=rswadmin

# Specifies the database connection password. This may be encrypted with the secure-cookie-key.
# The encrypted password can be generated using the helper command rstudio-server encrypt-password.
# It is strongly recommended that you encrypt the password!
password=<****>

# Specifies the maximum amount of seconds allowed before a database connection attempt
# is considered failed. The default if not specified is 10 seconds. Corresponds to the
# PostgreSQL "connect_timeout=" connection string parameter. 
connection-timeout-seconds=12
```

#### `/etc/rstudio/secure-cookie-key`

Generate a new cookie:

```bash
sudo apt-get install -y uuid
sudo sh -c "echo `uuid` > /mnt/efs/rstudio-server/secure-cookie-key"
sudo chmod 0600 /mnt/efs/rstudio-server/secure-cookie-key
```

You only need to run this command once from any server becaues the cookie is being written to the NFS mount.

### Step 6: Restart everything

```bash

```