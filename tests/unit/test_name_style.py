import pytest

from adaptix import NameStyle
from adaptix._internal.name_style import convert_snake_style, is_snake_style


def test_is_snake_style():
    assert is_snake_style('a')
    assert is_snake_style('a_b')
    assert is_snake_style('a_')
    assert is_snake_style('_a')
    assert is_snake_style('a_b_')
    assert is_snake_style('_a_')
    assert is_snake_style('_a_b')
    assert is_snake_style('_a_b_')

    assert is_snake_style('1')
    assert is_snake_style('1_2')
    assert is_snake_style('1_')
    assert is_snake_style('_1')
    assert is_snake_style('1_2_')
    assert is_snake_style('_1_')
    assert is_snake_style('_1_2')
    assert is_snake_style('_1_2_')

    assert is_snake_style('a_1')
    assert is_snake_style('a_1_')

    assert is_snake_style('a__b')
    assert is_snake_style('a__b_')

    assert is_snake_style('_')
    assert is_snake_style('___')

    assert is_snake_style('A_1_')
    assert is_snake_style('Aa_1_')

    assert not is_snake_style('123%')
    assert not is_snake_style('_123%')


def check_conversion(style, maps):
    for src, trg in maps.items():
        assert convert_snake_style(src, style) == trg


def test_snake_case_conversion():
    check_conversion(
        NameStyle.LOWER,
        {
            'abc_xyz': 'abcxyz',
            'abc__xyz': 'abcxyz',
            'abc_xyz_': 'abcxyz_',
            '_abc_xyz': '_abcxyz',
            '_abc_xyz_': '_abcxyz_',
            '_abc__xyz_': '_abcxyz_',
            'ABC_XYZ': 'abcxyz',
        }
    )
    check_conversion(
        NameStyle.CAMEL,
        {
            'abc_xyz': 'abcXyz',
            'abc__xyz': 'abcXyz',
            'abc_xyz_': 'abcXyz_',
            '_abc_xyz': '_abcXyz',
            '_abc_xyz_': '_abcXyz_',
            '_abc__xyz_': '_abcXyz_',
            'ABC_XYZ': 'abcXyz',
        }
    )
    check_conversion(
        NameStyle.PASCAL,
        {
            'abc_xyz': 'AbcXyz',
            'abc__xyz': 'AbcXyz',
            'abc_xyz_': 'AbcXyz_',
            '_abc_xyz': '_AbcXyz',
            '_abc_xyz_': '_AbcXyz_',
            '_abc__xyz_': '_AbcXyz_',
            'ABC_XYZ': 'AbcXyz',
        }
    )
    check_conversion(
        NameStyle.UPPER,
        {
            'abc_xyz': 'ABCXYZ',
            'abc__xyz': 'ABCXYZ',
            'abc_xyz_': 'ABCXYZ_',
            '_abc_xyz': '_ABCXYZ',
            '_abc_xyz_': '_ABCXYZ_',
            '_abc__xyz_': '_ABCXYZ_',
            'ABC_XYZ': 'ABCXYZ',
        }
    )

    check_conversion(
        NameStyle.LOWER_DOT,
        {
            'abc_xyz': 'abc.xyz',
            'abc__xyz': 'abc..xyz',
            'abc_xyz_': 'abc.xyz_',
            '_abc_xyz': '_abc.xyz',
            '_abc_xyz_': '_abc.xyz_',
            '_abc__xyz_': '_abc..xyz_',
            'ABC_XYZ': 'abc.xyz',
        }
    )
    check_conversion(
        NameStyle.CAMEL_DOT,
        {
            'abc_xyz': 'abc.Xyz',
            'abc__xyz': 'abc..Xyz',
            'abc_xyz_': 'abc.Xyz_',
            '_abc_xyz': '_abc.Xyz',
            '_abc_xyz_': '_abc.Xyz_',
            '_abc__xyz_': '_abc..Xyz_',
            'ABC_XYZ': 'abc.Xyz',
        }
    )
    check_conversion(
        NameStyle.PASCAL_DOT,
        {
            'abc_xyz': 'Abc.Xyz',
            'abc__xyz': 'Abc..Xyz',
            'abc_xyz_': 'Abc.Xyz_',
            '_abc_xyz': '_Abc.Xyz',
            '_abc_xyz_': '_Abc.Xyz_',
            '_abc__xyz_': '_Abc..Xyz_',
            'ABC_XYZ': 'Abc.Xyz',
        }
    )
    check_conversion(
        NameStyle.UPPER_DOT,
        {
            'abc_xyz': 'ABC.XYZ',
            'abc__xyz': 'ABC..XYZ',
            'abc_xyz_': 'ABC.XYZ_',
            '_abc_xyz': '_ABC.XYZ',
            '_abc_xyz_': '_ABC.XYZ_',
            '_abc__xyz_': '_ABC..XYZ_',
            'ABC_XYZ': 'ABC.XYZ',
        }
    )


def test_snake_case_conversion_fail():
    for style in NameStyle:
        with pytest.raises(ValueError):
            convert_snake_style('', style)

    for style in NameStyle:
        with pytest.raises(ValueError):
            convert_snake_style('___', style)

    for style in NameStyle:
        for name in ['abcxyz?']:
            with pytest.raises(ValueError):
                convert_snake_style(name, style)
