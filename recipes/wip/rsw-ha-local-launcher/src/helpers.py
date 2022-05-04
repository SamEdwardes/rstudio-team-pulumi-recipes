import os
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple

import pulumi
from pulumi_aws import ec2


import base64

@dataclass
class BaseConfig:
    ec2_size: str = 't3.medium'
    ami_id: str = 'ami-0aee2d0182c9054ac'
    vpc_group_ids: Optional[List[str]] = None
    key: Optional[Any] = None
    key_pair: Optional[ec2.KeyPair] = None
    private_key: Optional[Any] = None


def decode_key(key):
    """
    The privateKey associated with the selected key must be provided (either 
    directly or base64 encoded)
    """
    try:
        key = base64.b64decode(key.encode('ascii')).decode('ascii')
    except:
        pass
    if key.startswith('-----BEGIN RSA PRIVATE KEY-----'):
        return key
    return key.encode('ascii')


def get_key_pair(config: pulumi.Config) -> ec2.KeyPair:
    key_name = config.get('keyName')
    public_key = config.get('publicKey')
    if key_name is None:
        return ec2.KeyPair('key-rsw-ha', public_key=public_key)