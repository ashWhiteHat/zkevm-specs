from py_ecc.bn128 import is_on_curve, FQ
from zkevm_specs.util import (
    BN128Point,
    BN128_B,
    new_gfp,
    marshal,
    unmarshal,
    unmarshal_field,
    random_bn128_point,
)


def test_marshal_and_unmarshal():
    r = (0xD35D438DC58F0D9D, 0x0A78EB28F5C70B3D, 0x666EA36F7879462C, 0x0E0A77C19A07DF2F)
    one = new_gfp(1)
    assert r == one
