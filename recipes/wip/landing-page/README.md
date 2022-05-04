# Landing Page

A landing page for RStudio Team.

## Running the code

> For reference see: <https://github.com/pulumi/examples/blob/master/aws-py-ec2-provisioners/README.md?plain=1>

Next, generate an OpenSSH keypair for use with your server - as per the AWS [Requirements][1]

```
ssh-keygen -t rsa -f rsa -b 4096 -m PEM
```

This will output two files, `rsa` and `rsa.pub`, in the current directory. Be sure not to commit these files!

We then need to configure our stack so that the public key is used by our EC2 instance, and the private key used
for subsequent SCP and SSH steps that will configure our server after it is stood up.

```
cat rsa.pub | pulumi config set publicKey --
cat rsa | pulumi config set privateKey --secret --
```

Notice that we've used `--secret` for `privateKey`. This ensures their are stored in encrypted form in the Pulumi secrets system.

Also set your desired AWS region:

```
pulumi config set aws:region ca-central-1
```

From there, you can run `pulumi up` and all resources will be provisioned and configured.

## Setting up HTTPS

<https://certbot.eff.org/instructions?ws=nginx&os=ubuntufocal>
