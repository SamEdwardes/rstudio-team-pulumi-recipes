# for parameter iamInstanceProfile.name is invalid. Invalid IAM Instance Profile name
# aws ssm get-parameters --names test-param --with-decryption --region=ca-central-1
# aws ssm get-parameters --region ca-central-1 --names testParam --with-decryption --query Parameters[0].Value

def make_iam_role(tags):
    get_params_role = iam.Role(
        "samedwardes-rsw-ha-role",
        assume_role_policy=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
                }
            ]
        }),
        inline_policies=[
            iam.RoleInlinePolicyArgs(
                name="access_param_store",
                policy=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Action": [
                            "ssm:DescribeParameters", 
                            "ssm:GetParameters",
                            "kms:Decrypt"
                        ],
                        "Effect": "Allow",
                        "Resource": "*",
                    }],
                }),
            ),
        ],
        tags=tags
    )
    return get_params_role