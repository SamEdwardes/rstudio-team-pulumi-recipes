import os
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Dict, List, Optional, Tuple

import pulumi
from pulumi_aws import ec2
from pulumi_tls import PrivateKey
from rich import inspect, print

import base64

@dataclass
class BaseConfig:
    ec2_size: str = 't3.medium'
    ami_id: str = 'ami-0aee2d0182c9054ac'
    vpc_group_ids: List[str] = field(default_factory=lambda: ['sg-03d68a6b9f6a7d5d4'])
    tags: Dict[str, str] = field(default_factory=lambda: {
            "rs:environment": "development",
            "rs:owner": "sam.edwardes@rstudio.com",
            "rs:project": "solutions",
    })
    key: Optional[PrivateKey] = None
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
    

def dep(dependencies: List[Any]):
    """
    Helper function to define dependencies
    """
    return pulumi.ResourceOptions(depends_on=dependencies)