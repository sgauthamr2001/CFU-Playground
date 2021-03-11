#!/bin/env python
# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from util import DualPortMemory
from .post_process import PostProcessXetter, SRDHMInstruction, RoundingDividebyPOTInstruction
from .param_store import CircularIncrementer, ParamStoreSetter
from .registerfile import RegisterFileInstruction, RegisterSetter

from nmigen_cfu import Cfu

OUTPUT_CHANNEL_PARAM_DEPTH = 512


class Mnv2RegisterInstruction(RegisterFileInstruction):

    def _make_setter(self, m, reg_num, name):
        """Constructs and registers a setter.

        Return a pair of signals from setter: (value, set)
        """
        setter = RegisterSetter()
        m.submodules[name] = setter
        self.register_xetter(reg_num, setter)
        return setter.value, setter.set

    def _make_output_channel_param_store(
            self, m, reg_num, name, restart_signal):
        """Constructs and registers a param store connected to a memory
        and a circular incrementer.

        Returns a pair of signals: (current data, inc.next)
        """
        m.submodules[f'{name}_dp'] = dp = DualPortMemory(
            width=32, depth=OUTPUT_CHANNEL_PARAM_DEPTH, is_sim=not bool(self.platform))
        m.submodules[f'{name}_inc'] = inc = CircularIncrementer(
            OUTPUT_CHANNEL_PARAM_DEPTH)
        m.submodules[f'{name}_set'] = psset = ParamStoreSetter(
            32, OUTPUT_CHANNEL_PARAM_DEPTH)
        self.register_xetter(reg_num, psset)
        m.d.comb += [
            # Restart param store when reg is set
            psset.restart.eq(restart_signal),
            inc.restart.eq(restart_signal),
            # Incrementer is limited to number of items already set
            inc.limit.eq(psset.count),
            # Hook memory up to various components
            dp.r_addr.eq(inc.r_addr),
            dp.w_en.eq(psset.w_en),
            dp.w_addr.eq(psset.w_addr),
            dp.w_data.eq(psset.w_data),
        ]
        return dp.r_data, inc.next

    def elab_xetters(self, m):
        self._make_setter(m, 10, 'set_input_depth')
        self._make_setter(m, 11, 'set_output_depth')
        self._make_setter(m, 12, 'set_input_offset')
        offset, _ = self._make_setter(m, 13, 'set_output_offset')
        activation_min, _ = self._make_setter(m, 14, 'set_activation_min')
        activation_max, _ = self._make_setter(m, 15, 'set_activation_max')
        _, restart = self._make_setter(m, 20, 'set_output_batch_size')
        multiplier, multiplier_next = self._make_output_channel_param_store(
            m, 21, 'store_output_mutiplier', restart)
        shift, shift_next = self._make_output_channel_param_store(
            m, 22, 'store_output_shift', restart)
        bias, bias_next = self._make_output_channel_param_store(
            m, 23, 'store_output_bias', restart)
        m.submodules['ppx'] = ppx = PostProcessXetter()
        self.register_xetter(120, ppx)

        m.d.comb += [
            ppx.offset.eq(offset),
            ppx.activation_min.eq(activation_min),
            ppx.activation_max.eq(activation_max),
            ppx.bias.eq(bias),
            bias_next.eq(ppx.bias_next),
            ppx.multiplier.eq(multiplier),
            multiplier_next.eq(ppx.multiplier_next),
            ppx.shift.eq(shift),
            shift_next.eq(ppx.shift_next),
        ]


class Mnv2Cfu(Cfu):
    """Simple CFU for Mnv2.

    Most functionality is provided through a single set of registers.
    """

    def __init__(self):
        super().__init__({
            0: Mnv2RegisterInstruction(),
            6: RoundingDividebyPOTInstruction(),
            7: SRDHMInstruction(),
        })

    def elab(self, m):
        super().elab(m)


def make_cfu():
    return Mnv2Cfu()