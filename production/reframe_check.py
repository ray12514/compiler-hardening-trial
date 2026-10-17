"""Thin ReFrame adapter: the production controller owns all paired execution."""

import json
import os
from pathlib import Path
import shlex

import reframe as rfm
import reframe.utility.sanity as sn
from reframe.core.builtins import run_before, sanity_function


@rfm.simple_test
class LibraryWorkflow(rfm.RunOnlyRegressionTest):
    valid_systems = ['hardening-workflow:allocation']
    valid_prog_environs = ['controller']
    sourcesdir = None
    tags = {'hardening','library-workflow'}

    @run_before('run')
    def configure(self):
        command = json.loads(os.environ['TRIAL_PRODUCTION_COMMAND'])
        self.executable = shlex.quote(command[0])
        self.executable_opts = [shlex.quote(value) for value in command[1:]]
        self._pointer = Path(os.environ['TRIAL_PRODUCTION_POINTER'])

    @run_before('sanity')
    def collect(self):
        self._summary = None
        self.perf_variables = {}
        if not self._pointer.is_file():
            return
        out = Path(json.loads(self._pointer.read_text())['campaign'])
        self._summary = json.loads((out/'summary.json').read_text())
        # Keep one figure per condition and metric; never pool node layouts.
        for row in self._summary['summaries']:
            metrics = (('full_mean',row['unit']),('reference_mean',row['unit']),
                       ('deterioration_percent','%'),('interval_low_percent','%'),
                       ('interval_high_percent','%'),('pairs','pairs')) if 'unit' in row else (
                                 ('full_mean_seconds','s'),('reference_mean_seconds','s'),
                                 ('delta_seconds','s'),('runtime_increase_percent','%'),
                                 ('interval_low_percent','%'),('interval_high_percent','%'),('pairs','pairs'))
            for metric, unit in metrics:
                if row[metric] is not None:
                    self.perf_variables[row['condition']+'/'+metric] = sn.make_performance_function(
                        lambda value=row[metric]: value, unit)

    @sanity_function
    def completed(self):
        return sn.all([sn.assert_eq(self.job.exitcode,0),
                       sn.assert_true(self._summary is not None),
                       sn.assert_eq((self._summary or {}).get('status'),'finished')])
