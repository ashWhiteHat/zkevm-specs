from typing import Optional, Sequence, Tuple, Union, List

from ..instruction import Instruction, Transition
from ..table import (
    AccountFieldTag,
    BlockContextFieldTag,
    BytecodeFieldTag,
    CallContextFieldTag,
    FixedTableRow,
    RWTableRow,
    Tables,
    FixedTableTag,
    TxContextFieldTag,
    RW,
    RWTableTag,
    TxLogFieldTag,
    TxReceiptFieldTag,
    CopyDataTypeTag,
)
from ...util import FQ, N_BYTES_MEMORY_ADDRESS, N_BYTES_MEMORY_SIZE, IdentityPerWordGas


def dataCopy(instruction: Instruction):
    opcode = instruction.opcode_lookup(True)

    call_data_offset = instruction.call_context_lookup(CallContextFieldTag.CallDataOffset, RW.Read)
    call_data_length = instruction.call_context_lookup(CallContextFieldTag.CallDataLength, RW.Read)
    return_data_offset = instruction.call_context_lookup(
        CallContextFieldTag.ReturnDataOffset, RW.Read
    )
    return_data_length = instruction.call_context_lookup(
        CallContextFieldTag.ReturnDataLength, RW.Read
    )

    opcall_call_id = instruction.curr.call_id
    precompile_call_id = instruction.next.call_id

    # Copy current call data to return data
    size = call_data_length.expr()
    copy_rwc_inc, _ = instruction.copy_lookup(
        opcall_call_id,
        CopyDataTypeTag.Memory,
        opcall_call_id,
        CopyDataTypeTag.Memory,
        call_data_offset,
        call_data_offset + size,
        return_data_offset,
        return_data_offset + return_data_length.expr(),
        instruction.curr.rw_counter + instruction.rw_counter_offset,
    )

    # Copy current call data to next call context memory
    copy_rwc_inc, _ = instruction.copy_lookup(
        opcall_call_id,
        CopyDataTypeTag.Memory,
        precompile_call_id,
        CopyDataTypeTag.Memory,
        call_data_offset,
        call_data_offset + size,
        FQ(0),
        return_data_length,
        instruction.curr.rw_counter + instruction.rw_counter_offset,
    )

    # Update last callee information
    for (field_tag, expected_value) in [
        (CallContextFieldTag.LastCalleeId, precompile_call_id),
        (CallContextFieldTag.LastCalleeReturnDataOffset, FQ(0)),
        (CallContextFieldTag.LastCalleeReturnDataLength, size),
    ]:
        instruction.constrain_equal(
            instruction.call_context_lookup(field_tag, RW.Write, call_id=opcall_call_id),
            expected_value,
        )

    gas_cost = instruction.memory_copier_gas_cost(call_data_length, FQ(0), IdentityPerWordGas)

    instruction.step_state_transition_in_same_context(
        opcode,
        rw_counter=Transition.delta(instruction.rw_counter_offset + copy_rwc_inc),
        program_counter=Transition.delta(0),
        stack_pointer=Transition.delta(0),
        memory_size=Transition.to(size),
        dynamic_gas_cost=gas_cost,
    )
