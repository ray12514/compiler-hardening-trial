"""Run the existing campaign controller locally within its current allocation."""

import os
from pathlib import Path

site_configuration = {
    'systems': [{'name':'hardening-workflow','descr':'Existing Slurm allocation',
                 'hostnames':['.*'],
                 'partitions':[{'name':'allocation','scheduler':'local','launcher':'local',
                                'environs':['controller']}]}],
    'environments':[{'name':'controller'}],
    'general':[{'topology_prefix':str(Path(os.environ['TRIAL_PRODUCTION_POINTER']).parent/'topology')}],
}
