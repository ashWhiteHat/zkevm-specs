from ...util import (
    FQ,
    TxDataNonZeroGasEIP2028,
    MAX_U64,
    N_BYTES_U64,
    TxGas,
    TxGasContractCreation,
    TxDataZeroGas,
)
from ..instruction import Instruction, Transition
from ..table import CallContextFieldTag
from ..opcode import Opcode


def error_gas_uint_overflow(instruction: Instruction):
    opcode = instruction.opcode_lookup(True)

    (
        is_call,
        is_callcode,
        is_delegatecall,
        is_staticcall,
        is_create_flag,
        is_create2_flag,
        is_calldatacopy,
        is_codecopy,
        is_extcodecopy,
        is_returndatacopy,
        is_log0,
        is_log1,
        is_log2,
        is_log3,
        is_log4,
        is_sha3,
        is_exp,
        is_mload,
        is_mstore,
        is_mstore8,
        is_return,
        is_revert,
    ) = instruction.multiple_select(
        opcode,
        (
            Opcode.CALL,
            Opcode.CALLCODE,
            Opcode.DELEGATECALL,
            Opcode.STATICCALL,
            Opcode.CREATE,
            Opcode.CREATE2,
            Opcode.CALLDATACOPY,
            Opcode.CODECOPY,
            Opcode.EXTCODECOPY,
            Opcode.RETURNDATACOPY,
            Opcode.LOG0,
            Opcode.LOG1,
            Opcode.LOG2,
            Opcode.LOG3,
            Opcode.LOG4,
            Opcode.SHA3,
            Opcode.EXP,
            Opcode.MLOAD,
            Opcode.MSTORE,
            Opcode.MSTORE8,
            Opcode.RETURN,
            Opcode.REVERT,
        ),
    )
    is_create = is_create_flag + is_create2_flag
    is_dynamic_gas = (
        is_calldatacopy
        + is_codecopy
        + is_extcodecopy
        + is_returndatacopy
        + is_sha3
        + is_call
        + is_delegatecall
        + is_staticcall
        + is_create_flag
        + is_create2_flag
        + is_log0
        + is_log1
        + is_log2
        + is_log3
        + is_log4
        + is_mload
        + is_mstore
        + is_mstore8
        + is_return
        + is_revert
    )
    is_opcode_memory_size_overflow = (
        is_safe_mul_overflow
    ) = (
        is_call_gas_cost_overflow
    ) = (
        is_non_zero_calldata_gas_overflow
    ) = is_zero_calldata_gas_overflow = is_eip3860_overflow = FQ(0)

    # IntrinsicGas
    # https://github.com/ethereum/go-ethereum/blob/b946b7a13b749c99979e312c83dce34cac8dd7b1/core/state_transition.go#L67
    calldata_offset = instruction.call_context_lookup(CallContextFieldTag.CallDataOffset)
    calldata_length = instruction.call_context_lookup(CallContextFieldTag.CallDataLength)
    tx_id = instruction.call_context_lookup(CallContextFieldTag.TxId)
    data = [
        instruction.tx_calldata_lookup(tx_id, calldata_offset + FQ(idx))
        for idx in range(0, calldata_length.expr().n)
    ]
    dataLen = len(data)

    def transaction_data_gas_overflow():
        # zero and non-zero bytes are priced differently
        nz = len([byte for byte in data if byte != 0])
        gas = TxGasContractCreation if is_create == FQ(1) else TxGas
        is_non_zero_calldata_gas_overflow, _ = instruction.compare(
            FQ(((MAX_U64 - gas) // TxDataNonZeroGasEIP2028)), FQ(nz), N_BYTES_U64
        )
        gas += nz * TxDataNonZeroGasEIP2028

        # tx data zero gas overflow
        z = dataLen - nz
        is_zero_calldata_gas_overflow, _ = instruction.compare(
            FQ(((MAX_U64 - gas) // TxDataZeroGas)), FQ(z), N_BYTES_U64
        )

        # TODO: Would like to support EIP 3860 in the future (See
        # https://github.com/privacy-scaling-explorations/zkevm-specs/issues/421)
        # gas += z * TxDataZeroGas
        # if is_create:
        #     lenWords = dataLen // 32
        #     is_eip3860_overflow, _ = instruction.compare(
        #         FQ((MAX_U64 - gas) // InitCodeWordGas), FQ(lenWords), N_BYTES_U64
        #     )

    instruction.condition(FQ(dataLen > 0), transaction_data_gas_overflow)

    # Run
    # https://github.com/ethereum/go-ethereum/blob/b946b7a13b749c99979e312c83dce34cac8dd7b1/core/vm/interpreter.go#L105
    def dynamic_gas_overflow():
        (mem_size, is_opcode_memory_size_overflow) = instruction.memory_size(opcode)
        (_, is_safe_mul_overflow) = instruction.safe_mul(instruction.to_word_size(mem_size), 32)

    instruction.condition(is_dynamic_gas, dynamic_gas_overflow)

    # verify gas uint overflow.
    is_overflow = (
        is_opcode_memory_size_overflow
        + is_safe_mul_overflow
        + is_call_gas_cost_overflow
        + is_non_zero_calldata_gas_overflow
        + is_zero_calldata_gas_overflow
        + is_eip3860_overflow
    )
    instruction.constrain_not_zero(FQ(is_overflow))

    # verify call failure.
    instruction.constrain_equal(
        instruction.call_context_lookup(CallContextFieldTag.IsSuccess), FQ(0)
    )

    # state transition.
    if instruction.curr.is_root:
        # Do step state transition
        instruction.constrain_step_state_transition(
            rw_counter=Transition.delta(12),
            call_id=Transition.same(),
        )
    else:
        # when it is internal call, need to restore caller's state as finishing this call.
        # Restore caller state to next StepState
        instruction.step_state_transition_to_restored_context(
            rw_counter_delta=12,
            return_data_offset=FQ(0),
            return_data_length=FQ(0),
            gas_left=instruction.curr.gas_left,
        )