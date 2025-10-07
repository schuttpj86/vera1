# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0

import numpy as np
import pandas as pd
from VeraGridEngine.Simulations.results_table import ResultsTable
from VeraGridEngine.Simulations.results_template import ResultsTemplate
from VeraGridEngine.basic_structures import DateVec, IntVec, Vec
from VeraGridEngine.enumerations import StudyResultsType, ResultTypes, DeviceType


class ReliabilityResults(ResultsTemplate):

    def __init__(self, nsim: int):
        """
        Clustering Results constructor
        """
        ResultsTemplate.__init__(
            self,
            name='Reliability Analysis',
            available_results=[
                ResultTypes.ReliabilityLoleResults,
                ResultTypes.ReliabilityENSResults,
                ResultTypes.ReliabilityLOLFResults,
            ],
            clustering_results=None,
            time_array=None,
            study_results_type=StudyResultsType.Clustering
        )

        self.LOLE_evolution = np.zeros(nsim)
        self.ENS_evolution = np.zeros(nsim)
        self.LOLF_evolution = np.zeros(nsim)

        self.register(name='LOLE_evolution', tpe=Vec)
        self.register(name='ENS_evolution', tpe=Vec)
        self.register(name='LOLF_evolution', tpe=Vec)

    def mdl(self, result_type: ResultTypes) -> ResultsTable:
        """
        Plot the results.
        :param result_type: ResultTypes
        :return: ResultsModel
        """

        if result_type == ResultTypes.ReliabilityLoleResults:

            return ResultsTable(data=self.LOLE_evolution,
                                index=np.arange(len(self.LOLE_evolution), dtype=int),
                                columns=np.array(['LOLE']),
                                title=result_type.value,
                                units="MWh",
                                idx_device_type=DeviceType.NoDevice,
                                cols_device_type=DeviceType.NoDevice,
                                ylabel='hours/year')

        elif result_type == ResultTypes.ReliabilityENSResults:
            return ResultsTable(data=self.ENS_evolution,
                                index=np.arange(len(self.ENS_evolution), dtype=int),
                                columns=np.array(['ENS']),
                                title=result_type.value,
                                units="MWh",
                                idx_device_type=DeviceType.NoDevice,
                                cols_device_type=DeviceType.NoDevice,
                                ylabel='MWh/year')

        elif result_type == ResultTypes.ReliabilityLOLFResults:
            return ResultsTable(data=self.LOLF_evolution,
                                index=np.arange(len(self.LOLF_evolution), dtype=int),
                                columns=np.array(['LOLF']),
                                title=result_type.value,
                                units="nº of incidences",
                                idx_device_type=DeviceType.NoDevice,
                                cols_device_type=DeviceType.NoDevice,
                                ylabel='nº of incidences/year')

        else:
            raise Exception('Result type not understood:' + str(result_type))
