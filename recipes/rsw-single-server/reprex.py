import pulumi
from pulumi_aws import ec2
from pulumi_command import remote


def main():
    # Ubuntu Server 20.04 LTS (HVM), SSD Volume Type for us-east-2
    ami_id = "ami-0fb653ca2d3203ac1"
    key_pair = ec2.get_key_pair(key_pair_id="XXXX")

    rsw_server = ec2.Instance(
        f"rstudio-workbench-server",
        instance_type="t3.medium",
        ami=ami_id,                 
        key_name=key_pair.key_name
    )

    connection = remote.ConnectionArgs(
        host=rsw_server.public_dns, 
        user="ubuntu", 
        private_key="XXXX"
    )

    command_copy_justfile = remote.CopyFile(
        f"server-copy-justfile-",  
        local_path="server-side-justfile", 
        remote_path='justfile', 
        connection=connection, 
        opts=pulumi.ResourceOptions(depends_on=[rsw_server])
    )

main()