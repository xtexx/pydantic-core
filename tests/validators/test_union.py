import platform
import sys
from dataclasses import dataclass
from datetime import date, time
from enum import Enum, IntEnum
from itertools import permutations
from typing import Any, Optional, Union
from uuid import UUID

import pytest
from dirty_equals import IsFloat, IsInt

from pydantic_core import CoreConfig, SchemaError, SchemaValidator, ValidationError, core_schema

from ..conftest import plain_repr


@pytest.mark.parametrize(
    'input_value,expected_value',
    [
        (True, True),
        (False, False),
        ('true', True),
        ('false', False),
        (1, 1),
        (0, 0),
        (123, 123),
        ('123', 123),
        ('0', False),  # this case is different depending on the order of the choices
        ('1', True),  # this case is different depending on the order of the choices
    ],
)
def test_union_bool_int(input_value, expected_value):
    v = SchemaValidator(core_schema.union_schema(choices=[core_schema.bool_schema(), core_schema.int_schema()]))
    assert v.validate_python(input_value) == expected_value


@pytest.mark.parametrize(
    'input_value,expected_value',
    [
        (True, True),
        (False, False),
        ('true', True),
        ('false', False),
        (1, 1),
        (0, 0),
        (123, 123),
        ('123', 123),
        ('0', 0),  # this case is different depending on the order of the choices
        ('1', 1),  # this case is different depending on the order of the choices
    ],
)
def test_union_int_bool(input_value, expected_value):
    v = SchemaValidator(core_schema.union_schema(choices=[core_schema.int_schema(), core_schema.bool_schema()]))
    assert v.validate_python(input_value) == expected_value


class TestModelClass:
    class ModelA:
        pass

    class ModelB:
        pass

    @pytest.fixture(scope='class')
    def schema_validator(self) -> SchemaValidator:
        return SchemaValidator(
            schema=core_schema.union_schema(
                choices=[
                    core_schema.model_schema(
                        cls=self.ModelA,
                        schema=core_schema.model_fields_schema(
                            fields={
                                'a': core_schema.model_field(schema=core_schema.int_schema()),
                                'b': core_schema.model_field(schema=core_schema.str_schema()),
                            }
                        ),
                    ),
                    core_schema.model_schema(
                        cls=self.ModelB,
                        schema=core_schema.model_fields_schema(
                            fields={
                                'c': core_schema.model_field(schema=core_schema.int_schema()),
                                'd': core_schema.model_field(schema=core_schema.str_schema()),
                            }
                        ),
                    ),
                ]
            )
        )

    def test_model_a(self, schema_validator: SchemaValidator):
        m_a = schema_validator.validate_python({'a': 1, 'b': 'hello'})
        assert isinstance(m_a, self.ModelA)
        assert m_a.a == 1
        assert m_a.b == 'hello'

    def test_model_b(self, schema_validator: SchemaValidator):
        m_b = schema_validator.validate_python({'c': 2, 'd': 'again'})
        assert isinstance(m_b, self.ModelB)
        assert m_b.c == 2
        assert m_b.d == 'again'

    def test_exact_check(self, schema_validator: SchemaValidator):
        m_b = schema_validator.validate_python({'c': 2, 'd': 'again'})
        assert isinstance(m_b, self.ModelB)

        m_b2 = schema_validator.validate_python(m_b)
        assert m_b2 is m_b

    def test_error(self, schema_validator: SchemaValidator):
        with pytest.raises(ValidationError) as exc_info:
            schema_validator.validate_python({'a': 2})
        assert exc_info.value.errors(include_url=False) == [
            {'type': 'missing', 'loc': ('ModelA', 'b'), 'msg': 'Field required', 'input': {'a': 2}},
            {'type': 'missing', 'loc': ('ModelB', 'c'), 'msg': 'Field required', 'input': {'a': 2}},
            {'type': 'missing', 'loc': ('ModelB', 'd'), 'msg': 'Field required', 'input': {'a': 2}},
        ]


class TestModelClassSimilar:
    class ModelA:
        pass

    class ModelB:
        pass

    @pytest.fixture(scope='class')
    def schema_validator(self) -> SchemaValidator:
        return SchemaValidator(
            schema=core_schema.union_schema(
                choices=[
                    core_schema.model_schema(
                        cls=self.ModelA,
                        schema=core_schema.model_fields_schema(
                            fields={
                                'a': core_schema.model_field(schema=core_schema.int_schema()),
                                'b': core_schema.model_field(schema=core_schema.str_schema()),
                            }
                        ),
                    ),
                    core_schema.model_schema(
                        cls=self.ModelB,
                        schema=core_schema.model_fields_schema(
                            fields={
                                'a': core_schema.model_field(schema=core_schema.int_schema()),
                                'b': core_schema.model_field(schema=core_schema.str_schema()),
                                'c': core_schema.model_field(
                                    schema=core_schema.with_default_schema(
                                        schema=core_schema.float_schema(), default=1.0
                                    )
                                ),
                            }
                        ),
                    ),
                ]
            )
        )

    def test_model_a(self, schema_validator: SchemaValidator):
        m = schema_validator.validate_python({'a': 1, 'b': 'hello'})
        assert isinstance(m, self.ModelA)
        assert m.a == 1
        assert m.b == 'hello'
        assert not hasattr(m, 'c')

    def test_model_b_preferred(self, schema_validator: SchemaValidator):
        # Note, this is a different behavior to previous smart union behavior,
        # where the first match would be preferred. However, we believe is it better
        # to prefer the match with the greatest number of valid fields set.
        m = schema_validator.validate_python({'a': 1, 'b': 'hello', 'c': 2.0})
        assert isinstance(m, self.ModelB)
        assert m.a == 1
        assert m.b == 'hello'
        assert m.c == 2.0

    def test_model_b_not_ignored(self, schema_validator: SchemaValidator):
        m1 = self.ModelB()
        m1.a = 1
        m1.b = 'hello'
        m1.c = 2.0
        m2 = schema_validator.validate_python(m1)
        assert isinstance(m2, self.ModelB)
        assert m2.a == 1
        assert m2.b == 'hello'
        assert m2.c == 2.0


def test_nullable_via_union():
    v = SchemaValidator(core_schema.union_schema(choices=[core_schema.none_schema(), core_schema.int_schema()]))
    assert v.validate_python(None) is None
    assert v.validate_python(1) == 1
    with pytest.raises(ValidationError) as exc_info:
        v.validate_python('hello')
    assert exc_info.value.errors(include_url=False) == [
        {'type': 'none_required', 'loc': ('none',), 'msg': 'Input should be None', 'input': 'hello'},
        {
            'type': 'int_parsing',
            'loc': ('int',),
            'msg': 'Input should be a valid integer, unable to parse string as an integer',
            'input': 'hello',
        },
    ]


def test_union_list_bool_int():
    v = SchemaValidator(
        core_schema.union_schema(
            choices=[
                core_schema.list_schema(items_schema=core_schema.bool_schema()),
                core_schema.list_schema(items_schema=core_schema.int_schema()),
            ]
        )
    )
    assert v.validate_python(['true', True, 'no']) == [True, True, False]
    assert v.validate_python([5, 6, '789']) == [5, 6, 789]
    assert v.validate_python(['1', '0']) == [1, 0]
    with pytest.raises(ValidationError) as exc_info:
        v.validate_python([3, 'true'])
    assert exc_info.value.errors(include_url=False) == [
        {
            'type': 'bool_parsing',
            'loc': ('list[bool]', 0),
            'msg': 'Input should be a valid boolean, unable to interpret input',
            'input': 3,
        },
        {
            'type': 'int_parsing',
            'loc': ('list[int]', 1),
            'msg': 'Input should be a valid integer, unable to parse string as an integer',
            'input': 'true',
        },
    ]


@pytest.mark.xfail(
    platform.python_implementation() == 'PyPy' and sys.version_info[:2] == (3, 11), reason='pypy 3.11 type formatting'
)
def test_empty_choices():
    msg = r'Error building "union" validator:\s+SchemaError: One or more union choices required'
    with pytest.raises(SchemaError, match=msg):
        SchemaValidator(core_schema.union_schema(choices=[]))


def test_one_choice():
    v = SchemaValidator(core_schema.union_schema(choices=[core_schema.str_schema()]))
    assert (
        plain_repr(v)
        == 'SchemaValidator(title="str",validator=Str(StrValidator{strict:false,coerce_numbers_to_str:false}),definitions=[],cache_strings=True)'
    )
    assert v.validate_python('hello') == 'hello'


def test_strict_union_flag() -> None:
    v = SchemaValidator(core_schema.union_schema(choices=[core_schema.bool_schema(), core_schema.int_schema()]))
    assert v.validate_python(1, strict=True) == 1
    assert v.validate_python(123, strict=True) == 123

    with pytest.raises(ValidationError) as exc_info:
        v.validate_python('123', strict=True)

    assert exc_info.value.errors(include_url=False) == [
        {'type': 'bool_type', 'loc': ('bool',), 'msg': 'Input should be a valid boolean', 'input': '123'},
        {'type': 'int_type', 'loc': ('int',), 'msg': 'Input should be a valid integer', 'input': '123'},
    ]


def test_strict_union_config_level() -> None:
    v = SchemaValidator(
        core_schema.union_schema(choices=[core_schema.bool_schema(), core_schema.int_schema()]),
        config=CoreConfig(strict=True),
    )

    assert v.validate_python(1) == 1
    assert v.validate_python(123) == 123

    with pytest.raises(ValidationError) as exc_info:
        v.validate_python('123')
    assert exc_info.value.errors(include_url=False) == [
        {'type': 'bool_type', 'loc': ('bool',), 'msg': 'Input should be a valid boolean', 'input': '123'},
        {'type': 'int_type', 'loc': ('int',), 'msg': 'Input should be a valid integer', 'input': '123'},
    ]


def test_strict_union_member_level() -> None:
    v = SchemaValidator(
        core_schema.union_schema(choices=[core_schema.bool_schema(strict=True), core_schema.int_schema(strict=True)])
    )

    assert v.validate_python(1) == 1
    assert v.validate_python(123) == 123

    with pytest.raises(ValidationError) as exc_info:
        v.validate_python('123')
    assert exc_info.value.errors(include_url=False) == [
        {'type': 'bool_type', 'loc': ('bool',), 'msg': 'Input should be a valid boolean', 'input': '123'},
        {'type': 'int_type', 'loc': ('int',), 'msg': 'Input should be a valid integer', 'input': '123'},
    ]


def test_custom_error():
    v = SchemaValidator(
        core_schema.union_schema(
            choices=[core_schema.str_schema(), core_schema.bytes_schema()],
            custom_error_type='my_error',
            custom_error_message='Input should be a string or bytes',
        )
    )
    assert v.validate_python('hello') == 'hello'
    assert v.validate_python(b'hello') == b'hello'
    with pytest.raises(ValidationError) as exc_info:
        v.validate_python(123)
    # insert_assert(exc_info.value.errors(include_url=False))
    assert exc_info.value.errors(include_url=False) == [
        {'type': 'my_error', 'loc': (), 'msg': 'Input should be a string or bytes', 'input': 123}
    ]


def test_custom_error_type():
    v = SchemaValidator(
        core_schema.union_schema(
            choices=[core_schema.str_schema(), core_schema.bytes_schema()], custom_error_type='string_type'
        )
    )
    assert v.validate_python('hello') == 'hello'
    assert v.validate_python(b'hello') == b'hello'
    with pytest.raises(ValidationError) as exc_info:
        v.validate_python(123)
    # insert_assert(exc_info.value.errors(include_url=False))
    assert exc_info.value.errors(include_url=False) == [
        {'type': 'string_type', 'loc': (), 'msg': 'Input should be a valid string', 'input': 123}
    ]


def test_custom_error_type_context():
    v = SchemaValidator(
        core_schema.union_schema(
            choices=[core_schema.str_schema(), core_schema.bytes_schema()],
            custom_error_type='less_than',
            custom_error_context={'lt': 42},
        )
    )
    assert v.validate_python('hello') == 'hello'
    assert v.validate_python(b'hello') == b'hello'
    with pytest.raises(ValidationError) as exc_info:
        v.validate_python(123)
    # insert_assert(exc_info.value.errors(include_url=False))
    assert exc_info.value.errors(include_url=False) == [
        {'type': 'less_than', 'loc': (), 'msg': 'Input should be less than 42', 'input': 123, 'ctx': {'lt': 42.0}}
    ]


def test_dirty_behaviour():
    """
    Check dirty-equals does what we expect.
    """

    assert 1 == IsInt(approx=1, delta=0)
    assert 1.0 != IsInt(approx=1, delta=0)
    assert 1 != IsFloat(approx=1, delta=0)
    assert 1.0 == IsFloat(approx=1, delta=0)


def test_int_float():
    v = SchemaValidator(core_schema.union_schema([core_schema.int_schema(), core_schema.float_schema()]))
    assert v.validate_python(1) == IsInt(approx=1, delta=0)
    assert v.validate_json('1') == IsInt(approx=1, delta=0)
    assert v.validate_python(1.0) == IsFloat(approx=1, delta=0)
    assert v.validate_json('1.0') == IsFloat(approx=1, delta=0)

    v = SchemaValidator(core_schema.union_schema([core_schema.float_schema(), core_schema.int_schema()]))
    assert v.validate_python(1) == IsInt(approx=1, delta=0)
    assert v.validate_json('1') == IsInt(approx=1, delta=0)
    assert v.validate_python(1.0) == IsFloat(approx=1, delta=0)
    assert v.validate_json('1.0') == IsFloat(approx=1, delta=0)


def test_str_float():
    v = SchemaValidator(core_schema.union_schema([core_schema.str_schema(), core_schema.float_schema()]))

    assert v.validate_python(1) == IsFloat(approx=1, delta=0)
    assert v.validate_json('1') == IsFloat(approx=1, delta=0)
    assert v.validate_python(1.0) == IsFloat(approx=1, delta=0)
    assert v.validate_json('1.0') == IsFloat(approx=1, delta=0)

    assert v.validate_python('1.0') == '1.0'
    assert v.validate_python('1') == '1'
    assert v.validate_json('"1.0"') == '1.0'
    assert v.validate_json('"1"') == '1'

    v = SchemaValidator(core_schema.union_schema([core_schema.float_schema(), core_schema.str_schema()]))
    assert v.validate_python(1) == IsFloat(approx=1, delta=0)
    assert v.validate_json('1') == IsFloat(approx=1, delta=0)
    assert v.validate_python(1.0) == IsFloat(approx=1, delta=0)
    assert v.validate_json('1.0') == IsFloat(approx=1, delta=0)

    assert v.validate_python('1.0') == '1.0'
    assert v.validate_python('1') == '1'
    assert v.validate_json('"1.0"') == '1.0'
    assert v.validate_json('"1"') == '1'


def test_no_strict_check():
    v = SchemaValidator(core_schema.union_schema([core_schema.is_instance_schema(int), core_schema.json_schema()]))
    assert v.validate_python(123) == 123
    assert v.validate_python('[1, 2, 3]') == [1, 2, 3]


def test_strict_reference():
    v = SchemaValidator(
        core_schema.definitions_schema(
            core_schema.definition_reference_schema(schema_ref='tuple-ref'),
            [
                core_schema.tuple_positional_schema(
                    [
                        core_schema.float_schema(),
                        core_schema.union_schema(
                            [core_schema.int_schema(), core_schema.definition_reference_schema('tuple-ref')]
                        ),
                    ],
                    ref='tuple-ref',
                )
            ],
        )
    )

    assert repr(v.validate_python((1, 2))) == '(1.0, 2)'
    assert repr(v.validate_python((1.0, (2.0, 3)))) == '(1.0, (2.0, 3))'


def test_case_labels():
    v = SchemaValidator(
        core_schema.union_schema(
            choices=[core_schema.none_schema(), ({'type': 'int'}, 'my_label'), core_schema.str_schema()]
        )
    )
    assert v.validate_python(None) is None
    assert v.validate_python(1) == 1
    with pytest.raises(ValidationError, match=r'3 validation errors for union\[none,my_label,str]') as exc_info:
        v.validate_python(1.5)
    assert exc_info.value.errors(include_url=False) == [
        {'input': 1.5, 'loc': ('none',), 'msg': 'Input should be None', 'type': 'none_required'},
        {
            'input': 1.5,
            'loc': ('my_label',),
            'msg': 'Input should be a valid integer, got a number with a fractional part',
            'type': 'int_from_float',
        },
        {'input': 1.5, 'loc': ('str',), 'msg': 'Input should be a valid string', 'type': 'string_type'},
    ]


def test_left_to_right_doesnt_care_about_strict_check():
    v = SchemaValidator(
        core_schema.union_schema([core_schema.int_schema(), core_schema.json_schema()], mode='left_to_right')
    )
    assert 'strict_required' not in plain_repr(v)
    assert 'ultra_strict_required' not in plain_repr(v)


def test_left_to_right_union():
    choices = [core_schema.int_schema(), core_schema.float_schema()]

    # smart union prefers float
    v = SchemaValidator(core_schema.union_schema(choices, mode='smart'))
    out = v.validate_python(1.0)
    assert out == 1.0
    assert isinstance(out, float)

    # left_to_right union will select int
    v = SchemaValidator(core_schema.union_schema(choices, mode='left_to_right'))
    out = v.validate_python(1)
    assert out == 1
    assert isinstance(out, int)

    out = v.validate_python(1.0)
    assert out == 1
    assert isinstance(out, int)

    # reversing them will select float
    v = SchemaValidator(core_schema.union_schema(list(reversed(choices)), mode='left_to_right'))
    out = v.validate_python(1.0)
    assert out == 1.0
    assert isinstance(out, float)

    out = v.validate_python(1)
    assert out == 1.0
    assert isinstance(out, float)


def test_left_to_right_union_strict():
    choices = [core_schema.int_schema(strict=True), core_schema.float_schema(strict=True)]

    # left_to_right union will select not cast if int first (strict int will not accept float)
    v = SchemaValidator(core_schema.union_schema(choices, mode='left_to_right'))
    out = v.validate_python(1)
    assert out == 1
    assert isinstance(out, int)

    out = v.validate_python(1.0)
    assert out == 1.0
    assert isinstance(out, float)

    # reversing union will select float always (as strict float will accept int)
    v = SchemaValidator(
        core_schema.union_schema(
            list(reversed(choices)),
            mode='left_to_right',
        )
    )
    out = v.validate_python(1.0)
    assert out == 1.0
    assert isinstance(out, float)

    out = v.validate_python(1)
    assert out == 1.0
    assert isinstance(out, float)


def test_union_function_before_called_once():
    # See https://github.com/pydantic/pydantic/issues/6830 - in particular the
    # smart union validator used to call `remove_prefix` twice, which is not
    # ideal from a user perspective.
    class SpecialValues(str, Enum):
        DEFAULT = 'default'
        OTHER = 'other'

    special_values_schema = core_schema.no_info_after_validator_function(SpecialValues, core_schema.str_schema())

    validator_called_count = 0

    def remove_prefix(v: str):
        nonlocal validator_called_count
        validator_called_count += 1
        if v.startswith('uuid::'):
            return v[6:]
        return v

    prefixed_uuid_schema = core_schema.no_info_before_validator_function(remove_prefix, core_schema.uuid_schema())

    v = SchemaValidator(core_schema.union_schema([special_values_schema, prefixed_uuid_schema]))

    assert v.validate_python('uuid::12345678-1234-5678-1234-567812345678') == UUID(
        '12345678-1234-5678-1234-567812345678'
    )
    assert validator_called_count == 1


@pytest.mark.parametrize(
    ('schema', 'input_value', 'expected_value'),
    (
        (
            core_schema.uuid_schema(),
            '12345678-1234-5678-1234-567812345678',
            UUID('12345678-1234-5678-1234-567812345678'),
        ),
        (core_schema.date_schema(), '2020-01-01', date(2020, 1, 1)),
        (core_schema.time_schema(), '00:00:00', time(0, 0, 0)),
        # In V2.4 these already returned strings, so we keep this behaviour in V2
        (core_schema.datetime_schema(), '2020-01-01:00:00:00', '2020-01-01:00:00:00'),
        (core_schema.url_schema(), 'https://foo.com', 'https://foo.com'),
        (core_schema.multi_host_url_schema(), 'https://bar.com,foo.com', 'https://bar.com,foo.com'),
    ),
)
def test_smart_union_json_string_types(schema: core_schema.CoreSchema, input_value: str, expected_value: Any):
    # Many types have to be represented in strings as JSON, we make sure that
    # when parsing in JSON mode these types are preferred
    # TODO: in V3 we will make str win in all these cases.

    validator = SchemaValidator(core_schema.union_schema([schema, core_schema.str_schema()]))
    assert validator.validate_json(f'"{input_value}"') == expected_value
    # in Python mode the string will be preferred
    assert validator.validate_python(input_value) == input_value


@pytest.mark.parametrize(
    ('schema', 'input_value'),
    (
        pytest.param(
            core_schema.uuid_schema(),
            '12345678-1234-5678-1234-567812345678',
            marks=pytest.mark.xfail(reason='TODO: V3'),
        ),
        (core_schema.date_schema(), '2020-01-01'),
        (core_schema.time_schema(), '00:00:00'),
        (core_schema.datetime_schema(), '2020-01-01:00:00:00'),
        (core_schema.url_schema(), 'https://foo.com'),
        (core_schema.multi_host_url_schema(), 'https://bar.com,foo.com'),
    ),
)
def test_smart_union_json_string_types_str_first(schema: core_schema.CoreSchema, input_value: str):
    # As above, but reversed order; str should always win
    validator = SchemaValidator(core_schema.union_schema([core_schema.str_schema(), schema]))
    assert validator.validate_json(f'"{input_value}"') == input_value
    assert validator.validate_python(input_value) == input_value


def test_smart_union_default_fallback():
    """Using a default value does not affect the exactness of the smart union match."""

    class ModelA:
        x: int
        y: int = 1

    class ModelB:
        x: int

    schema = core_schema.union_schema(
        [
            core_schema.model_schema(
                ModelA,
                core_schema.model_fields_schema(
                    {
                        'x': core_schema.model_field(core_schema.int_schema()),
                        'y': core_schema.model_field(
                            core_schema.with_default_schema(core_schema.int_schema(), default=1)
                        ),
                    }
                ),
            ),
            core_schema.model_schema(
                ModelB, core_schema.model_fields_schema({'x': core_schema.model_field(core_schema.int_schema())})
            ),
        ]
    )

    validator = SchemaValidator(schema)

    result = validator.validate_python({'x': 1})
    assert isinstance(result, ModelA)
    assert result.x == 1
    assert result.y == 1

    # passing a ModelB explicitly will not match the default value
    b = ModelB()
    assert validator.validate_python(b) is b


def test_smart_union_model_field():
    class ModelA:
        x: int

    class ModelB:
        x: str

    schema = core_schema.union_schema(
        [
            core_schema.model_schema(
                ModelA, core_schema.model_fields_schema({'x': core_schema.model_field(core_schema.int_schema())})
            ),
            core_schema.model_schema(
                ModelB, core_schema.model_fields_schema({'x': core_schema.model_field(core_schema.str_schema())})
            ),
        ]
    )

    validator = SchemaValidator(schema)

    result = validator.validate_python({'x': 1})
    assert isinstance(result, ModelA)
    assert result.x == 1

    result = validator.validate_python({'x': '1'})
    assert isinstance(result, ModelB)
    assert result.x == '1'


def test_smart_union_dataclass_field():
    @dataclass
    class ModelA:
        x: int

    @dataclass
    class ModelB:
        x: str

    schema = core_schema.union_schema(
        [
            core_schema.dataclass_schema(
                ModelA,
                core_schema.dataclass_args_schema(
                    'ModelA', [core_schema.dataclass_field('x', core_schema.int_schema())]
                ),
                ['x'],
            ),
            core_schema.dataclass_schema(
                ModelB,
                core_schema.dataclass_args_schema(
                    'ModelB', [core_schema.dataclass_field('x', core_schema.str_schema())]
                ),
                ['x'],
            ),
        ]
    )

    validator = SchemaValidator(schema)

    result = validator.validate_python({'x': 1})
    assert isinstance(result, ModelA)
    assert result.x == 1

    result = validator.validate_python({'x': '1'})
    assert isinstance(result, ModelB)
    assert result.x == '1'


def test_smart_union_with_any():
    """any is preferred over lax validations"""

    # str not coerced to int
    schema = core_schema.union_schema([core_schema.int_schema(), core_schema.any_schema()])
    validator = SchemaValidator(schema)
    assert validator.validate_python('1') == '1'

    # int *is* coerced to float, this is a strict validation
    schema = core_schema.union_schema([core_schema.float_schema(), core_schema.any_schema()])
    validator = SchemaValidator(schema)
    assert repr(validator.validate_python(1)) == '1.0'


def test_smart_union_validator_function():
    """adding a validator function should not change smart union behaviour"""

    inner_schema = core_schema.union_schema([core_schema.int_schema(), core_schema.float_schema()])

    validator = SchemaValidator(inner_schema)
    assert repr(validator.validate_python(1)) == '1'
    assert repr(validator.validate_python(1.0)) == '1.0'

    schema = core_schema.union_schema(
        [core_schema.no_info_after_validator_function(lambda v: v * 2, inner_schema), core_schema.str_schema()]
    )

    validator = SchemaValidator(schema)
    assert repr(validator.validate_python(1)) == '2'
    assert repr(validator.validate_python(1.0)) == '2.0'
    assert validator.validate_python('1') == '1'

    schema = core_schema.union_schema(
        [
            core_schema.no_info_wrap_validator_function(lambda v, handler: handler(v) * 2, inner_schema),
            core_schema.str_schema(),
        ]
    )

    validator = SchemaValidator(schema)
    assert repr(validator.validate_python(1)) == '2'
    assert repr(validator.validate_python(1.0)) == '2.0'
    assert validator.validate_python('1') == '1'


def test_smart_union_validator_function_one_arm():
    """adding a validator function should not change smart union behaviour"""

    schema = core_schema.union_schema(
        [
            core_schema.float_schema(),
            core_schema.no_info_after_validator_function(lambda v: v * 2, core_schema.int_schema()),
        ]
    )

    validator = SchemaValidator(schema)
    assert repr(validator.validate_python(1)) == '2'
    assert repr(validator.validate_python(1.0)) == '1.0'

    schema = core_schema.union_schema(
        [
            core_schema.float_schema(),
            core_schema.no_info_wrap_validator_function(lambda v, handler: handler(v) * 2, core_schema.int_schema()),
        ]
    )

    validator = SchemaValidator(schema)
    assert repr(validator.validate_python(1)) == '2'
    assert repr(validator.validate_python(1.0)) == '1.0'


def test_int_not_coerced_to_enum():
    class BinaryEnum(IntEnum):
        ZERO = 0
        ONE = 1

    enum_schema = core_schema.lax_or_strict_schema(
        core_schema.no_info_after_validator_function(BinaryEnum, core_schema.int_schema()),
        core_schema.is_instance_schema(BinaryEnum),
    )

    schema = core_schema.union_schema([enum_schema, core_schema.int_schema()])

    validator = SchemaValidator(schema)

    assert validator.validate_python(0) is not BinaryEnum.ZERO
    assert validator.validate_python(1) is not BinaryEnum.ONE
    assert validator.validate_python(BinaryEnum.ZERO) is BinaryEnum.ZERO
    assert validator.validate_python(BinaryEnum.ONE) is BinaryEnum.ONE


def test_model_and_literal_union() -> None:
    # see https://github.com/pydantic/pydantic/issues/8183
    class ModelA:
        pass

    validator = SchemaValidator(
        core_schema.union_schema(
            choices=[
                core_schema.model_schema(
                    cls=ModelA,
                    schema=core_schema.model_fields_schema(
                        fields={'a': core_schema.model_field(schema=core_schema.int_schema())}
                    ),
                ),
                core_schema.literal_schema(expected=[True]),
            ]
        )
    )

    # validation against Literal[True] fails bc of the unhashable dict
    # A ValidationError is raised, not a ValueError, which allows the validation against the union to continue
    m = validator.validate_python({'a': 42})
    assert isinstance(m, ModelA)
    assert m.a == 42
    assert validator.validate_python(True) is True


def permute_choices(choices: list[core_schema.CoreSchema]) -> list[list[core_schema.CoreSchema]]:
    return [list(p) for p in permutations(choices)]


class TestSmartUnionWithSubclass:
    class ModelA:
        a: int

    class ModelB(ModelA):
        b: int

    model_a_schema = core_schema.model_schema(
        ModelA, core_schema.model_fields_schema(fields={'a': core_schema.model_field(core_schema.int_schema())})
    )
    model_b_schema = core_schema.model_schema(
        ModelB,
        core_schema.model_fields_schema(
            fields={
                'a': core_schema.model_field(core_schema.int_schema()),
                'b': core_schema.model_field(core_schema.int_schema()),
            }
        ),
    )

    @pytest.mark.parametrize('choices', permute_choices([model_a_schema, model_b_schema]))
    def test_more_specific_data_matches_subclass(self, choices) -> None:
        validator = SchemaValidator(core_schema.union_schema(choices))
        assert isinstance(validator.validate_python({'a': 1}), self.ModelA)
        assert isinstance(validator.validate_python({'a': 1, 'b': 2}), self.ModelB)

        assert isinstance(validator.validate_python({'a': 1, 'b': 2}), self.ModelB)

        # confirm that a model that matches in lax mode with 2 fields
        # is preferred over a model that matches in strict mode with 1 field
        assert isinstance(validator.validate_python({'a': '1', 'b': '2'}), self.ModelB)
        assert isinstance(validator.validate_python({'a': '1', 'b': 2}), self.ModelB)
        assert isinstance(validator.validate_python({'a': 1, 'b': '2'}), self.ModelB)


class TestSmartUnionWithDefaults:
    class ModelA:
        a: int = 0

    class ModelB:
        b: int = 0

    model_a_schema = core_schema.model_schema(
        ModelA,
        core_schema.model_fields_schema(
            fields={'a': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0))}
        ),
    )
    model_b_schema = core_schema.model_schema(
        ModelB,
        core_schema.model_fields_schema(
            fields={'b': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0))}
        ),
    )

    @pytest.mark.parametrize('choices', permute_choices([model_a_schema, model_b_schema]))
    def test_fields_set_ensures_best_match(self, choices) -> None:
        validator = SchemaValidator(core_schema.union_schema(choices))
        assert isinstance(validator.validate_python({'a': 1}), self.ModelA)
        assert isinstance(validator.validate_python({'b': 1}), self.ModelB)

        # defaults to leftmost choice if there's a tie
        assert isinstance(validator.validate_python({}), choices[0]['cls'])

    @pytest.mark.parametrize('choices', permute_choices([model_a_schema, model_b_schema]))
    def test_optional_union_with_members_having_defaults(self, choices) -> None:
        class WrapModel:
            val: Optional[Union[self.ModelA, self.ModelB]] = None

        val = SchemaValidator(
            schema=core_schema.model_schema(
                WrapModel,
                core_schema.model_fields_schema(
                    fields={
                        'val': core_schema.model_field(
                            core_schema.with_default_schema(
                                core_schema.union_schema(choices),
                                default=None,
                            )
                        )
                    }
                ),
            )
        )

        assert isinstance(val.validate_python({'val': {'a': 1}}).val, self.ModelA)
        assert isinstance(val.validate_python({'val': {'b': 1}}).val, self.ModelB)
        assert val.validate_python({}).val is None


def test_dc_smart_union_by_fields_set() -> None:
    @dataclass
    class ModelA:
        x: int

    @dataclass
    class ModelB(ModelA):
        y: int

    dc_a_schema = core_schema.dataclass_schema(
        ModelA,
        core_schema.dataclass_args_schema('ModelA', [core_schema.dataclass_field('x', core_schema.int_schema())]),
        ['x'],
    )

    dc_b_schema = core_schema.dataclass_schema(
        ModelB,
        core_schema.dataclass_args_schema(
            'ModelB',
            [
                core_schema.dataclass_field('x', core_schema.int_schema()),
                core_schema.dataclass_field('y', core_schema.int_schema()),
            ],
        ),
        ['x', 'y'],
    )

    for choices in permute_choices([dc_a_schema, dc_b_schema]):
        validator = SchemaValidator(core_schema.union_schema(choices=choices))

        assert isinstance(validator.validate_python({'x': 1}), ModelA)
        assert isinstance(validator.validate_python({'x': '1'}), ModelA)

        assert isinstance(validator.validate_python({'x': 1, 'y': 2}), ModelB)
        assert isinstance(validator.validate_python({'x': 1, 'y': '2'}), ModelB)
        assert isinstance(validator.validate_python({'x': '1', 'y': 2}), ModelB)
        assert isinstance(validator.validate_python({'x': '1', 'y': '2'}), ModelB)


def test_dc_smart_union_with_defaults() -> None:
    @dataclass
    class ModelA:
        a: int = 0

    @dataclass
    class ModelB:
        b: int = 0

    dc_a_schema = core_schema.dataclass_schema(
        ModelA,
        core_schema.dataclass_args_schema(
            'ModelA',
            [
                core_schema.dataclass_field(
                    'a', core_schema.with_default_schema(schema=core_schema.int_schema(), default=0)
                )
            ],
        ),
        ['a'],
    )

    dc_b_schema = core_schema.dataclass_schema(
        ModelB,
        core_schema.dataclass_args_schema(
            'ModelB',
            [
                core_schema.dataclass_field(
                    'b', core_schema.with_default_schema(schema=core_schema.int_schema(), default=0)
                )
            ],
        ),
        ['b'],
    )

    for choices in permute_choices([dc_a_schema, dc_b_schema]):
        validator = SchemaValidator(core_schema.union_schema(choices=choices))

        assert isinstance(validator.validate_python({'a': 1}), ModelA)
        assert isinstance(validator.validate_python({'b': 1}), ModelB)


def test_td_smart_union_by_fields_set() -> None:
    td_a_schema = core_schema.typed_dict_schema(
        fields={'x': core_schema.typed_dict_field(core_schema.int_schema())},
    )

    td_b_schema = core_schema.typed_dict_schema(
        fields={
            'x': core_schema.typed_dict_field(core_schema.int_schema()),
            'y': core_schema.typed_dict_field(core_schema.int_schema()),
        },
    )

    for choices in permute_choices([td_a_schema, td_b_schema]):
        validator = SchemaValidator(core_schema.union_schema(choices=choices))

        assert set(validator.validate_python({'x': 1}).keys()) == {'x'}
        assert set(validator.validate_python({'x': '1'}).keys()) == {'x'}

        assert set(validator.validate_python({'x': 1, 'y': 2}).keys()) == {'x', 'y'}
        assert set(validator.validate_python({'x': 1, 'y': '2'}).keys()) == {'x', 'y'}
        assert set(validator.validate_python({'x': '1', 'y': 2}).keys()) == {'x', 'y'}
        assert set(validator.validate_python({'x': '1', 'y': '2'}).keys()) == {'x', 'y'}


def test_smart_union_does_nested_model_field_counting() -> None:
    class SubModelA:
        x: int = 1

    class SubModelB:
        y: int = 2

    class ModelA:
        sub: SubModelA

    class ModelB:
        sub: SubModelB

    model_a_schema = core_schema.model_schema(
        ModelA,
        core_schema.model_fields_schema(
            fields={
                'sub': core_schema.model_field(
                    core_schema.model_schema(
                        SubModelA,
                        core_schema.model_fields_schema(
                            fields={
                                'x': core_schema.model_field(
                                    core_schema.with_default_schema(core_schema.int_schema(), default=1)
                                )
                            }
                        ),
                    )
                )
            }
        ),
    )

    model_b_schema = core_schema.model_schema(
        ModelB,
        core_schema.model_fields_schema(
            fields={
                'sub': core_schema.model_field(
                    core_schema.model_schema(
                        SubModelB,
                        core_schema.model_fields_schema(
                            fields={
                                'y': core_schema.model_field(
                                    core_schema.with_default_schema(core_schema.int_schema(), default=2)
                                )
                            }
                        ),
                    )
                )
            }
        ),
    )

    for choices in permute_choices([model_a_schema, model_b_schema]):
        validator = SchemaValidator(core_schema.union_schema(choices=choices))

        assert isinstance(validator.validate_python({'sub': {'x': 1}}), ModelA)
        assert isinstance(validator.validate_python({'sub': {'y': 3}}), ModelB)

        # defaults to leftmost choice if there's a tie
        assert isinstance(validator.validate_python({'sub': {}}), choices[0]['cls'])


def test_smart_union_does_nested_dataclass_field_counting() -> None:
    @dataclass
    class SubModelA:
        x: int = 1

    @dataclass
    class SubModelB:
        y: int = 2

    @dataclass
    class ModelA:
        sub: SubModelA

    @dataclass
    class ModelB:
        sub: SubModelB

    dc_a_schema = core_schema.dataclass_schema(
        ModelA,
        core_schema.dataclass_args_schema(
            'ModelA',
            [
                core_schema.dataclass_field(
                    'sub',
                    core_schema.with_default_schema(
                        core_schema.dataclass_schema(
                            SubModelA,
                            core_schema.dataclass_args_schema(
                                'SubModelA',
                                [
                                    core_schema.dataclass_field(
                                        'x', core_schema.with_default_schema(core_schema.int_schema(), default=1)
                                    )
                                ],
                            ),
                            ['x'],
                        ),
                        default=SubModelA(),
                    ),
                )
            ],
        ),
        ['sub'],
    )

    dc_b_schema = core_schema.dataclass_schema(
        ModelB,
        core_schema.dataclass_args_schema(
            'ModelB',
            [
                core_schema.dataclass_field(
                    'sub',
                    core_schema.with_default_schema(
                        core_schema.dataclass_schema(
                            SubModelB,
                            core_schema.dataclass_args_schema(
                                'SubModelB',
                                [
                                    core_schema.dataclass_field(
                                        'y', core_schema.with_default_schema(core_schema.int_schema(), default=2)
                                    )
                                ],
                            ),
                            ['y'],
                        ),
                        default=SubModelB(),
                    ),
                )
            ],
        ),
        ['sub'],
    )

    for choices in permute_choices([dc_a_schema, dc_b_schema]):
        validator = SchemaValidator(core_schema.union_schema(choices=choices))

        assert isinstance(validator.validate_python({'sub': {'x': 1}}), ModelA)
        assert isinstance(validator.validate_python({'sub': {'y': 3}}), ModelB)

        # defaults to leftmost choice if there's a tie
        assert isinstance(validator.validate_python({'sub': {}}), choices[0]['cls'])


def test_smart_union_does_nested_typed_dict_field_counting() -> None:
    td_a_schema = core_schema.typed_dict_schema(
        fields={
            'sub': core_schema.typed_dict_field(
                core_schema.typed_dict_schema(fields={'x': core_schema.typed_dict_field(core_schema.int_schema())})
            )
        }
    )

    td_b_schema = core_schema.typed_dict_schema(
        fields={
            'sub': core_schema.typed_dict_field(
                core_schema.typed_dict_schema(fields={'y': core_schema.typed_dict_field(core_schema.int_schema())})
            )
        }
    )

    for choices in permute_choices([td_a_schema, td_b_schema]):
        validator = SchemaValidator(core_schema.union_schema(choices=choices))

        assert set(validator.validate_python({'sub': {'x': 1}})['sub'].keys()) == {'x'}
        assert set(validator.validate_python({'sub': {'y': 2}})['sub'].keys()) == {'y'}


def test_nested_unions_bubble_up_field_count() -> None:
    class SubModelX:
        x1: int = 0
        x2: int = 0
        x3: int = 0

    class SubModelY:
        x1: int = 0
        x2: int = 0
        x3: int = 0

    class SubModelZ:
        z1: int = 0
        z2: int = 0
        z3: int = 0

    class SubModelW:
        w1: int = 0
        w2: int = 0
        w3: int = 0

    class ModelA:
        a: Union[SubModelX, SubModelY]

    class ModelB:
        b: Union[SubModelZ, SubModelW]

    model_x_schema = core_schema.model_schema(
        SubModelX,
        core_schema.model_fields_schema(
            fields={
                'x1': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'x2': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'x3': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
            }
        ),
    )

    model_y_schema = core_schema.model_schema(
        SubModelY,
        core_schema.model_fields_schema(
            fields={
                'x1': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'x2': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'x3': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
            }
        ),
    )

    model_z_schema = core_schema.model_schema(
        SubModelZ,
        core_schema.model_fields_schema(
            fields={
                'z1': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'z2': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'z3': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
            }
        ),
    )

    model_w_schema = core_schema.model_schema(
        SubModelW,
        core_schema.model_fields_schema(
            fields={
                'w1': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'w2': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
                'w3': core_schema.model_field(core_schema.with_default_schema(core_schema.int_schema(), default=0)),
            }
        ),
    )

    model_a_schema_options = [
        core_schema.union_schema([model_x_schema, model_y_schema]),
        core_schema.union_schema([model_y_schema, model_x_schema]),
    ]

    model_b_schema_options = [
        core_schema.union_schema([model_z_schema, model_w_schema]),
        core_schema.union_schema([model_w_schema, model_z_schema]),
    ]

    for model_a_schema in model_a_schema_options:
        for model_b_schema in model_b_schema_options:
            validator = SchemaValidator(
                schema=core_schema.union_schema(
                    [
                        core_schema.model_schema(
                            ModelA,
                            core_schema.model_fields_schema(fields={'a': core_schema.model_field(model_a_schema)}),
                        ),
                        core_schema.model_schema(
                            ModelB,
                            core_schema.model_fields_schema(fields={'b': core_schema.model_field(model_b_schema)}),
                        ),
                    ]
                )
            )

            result = validator.validate_python(
                {'a': {'x1': 1, 'x2': 2, 'y1': 1, 'y2': 2}, 'b': {'w1': 1, 'w2': 2, 'w3': 3}}
            )
            assert isinstance(result, ModelB)
            assert isinstance(result.b, SubModelW)


@pytest.mark.parametrize('extra_behavior', ['forbid', 'ignore', 'allow'])
def test_smart_union_extra_behavior(extra_behavior) -> None:
    class Foo:
        foo: str = 'foo'

    class Bar:
        bar: str = 'bar'

    class Model:
        x: Union[Foo, Bar]

    validator = SchemaValidator(
        core_schema.model_schema(
            Model,
            core_schema.model_fields_schema(
                fields={
                    'x': core_schema.model_field(
                        core_schema.union_schema(
                            [
                                core_schema.model_schema(
                                    Foo,
                                    core_schema.model_fields_schema(
                                        fields={
                                            'foo': core_schema.model_field(
                                                core_schema.with_default_schema(core_schema.str_schema(), default='foo')
                                            )
                                        }
                                    ),
                                    extra_behavior=extra_behavior,
                                ),
                                core_schema.model_schema(
                                    Bar,
                                    core_schema.model_fields_schema(
                                        fields={
                                            'bar': core_schema.model_field(
                                                core_schema.with_default_schema(core_schema.str_schema(), default='bar')
                                            )
                                        }
                                    ),
                                    extra_behavior=extra_behavior,
                                ),
                            ]
                        )
                    )
                }
            ),
        )
    )

    assert isinstance(validator.validate_python({'x': {'foo': 'foo'}}).x, Foo)
    assert isinstance(validator.validate_python({'x': {'bar': 'bar'}}).x, Bar)


def test_smart_union_wrap_validator_should_not_change_nested_model_field_counts() -> None:
    """Adding a wrap validator on a union member should not affect smart union behavior"""

    class SubModel:
        x: str = 'x'

    class ModelA:
        type: str = 'A'
        sub: SubModel

    class ModelB:
        type: str = 'B'
        sub: SubModel

    submodel_schema = core_schema.model_schema(
        SubModel,
        core_schema.model_fields_schema(fields={'x': core_schema.model_field(core_schema.str_schema())}),
    )

    wrapped_submodel_schema = core_schema.no_info_wrap_validator_function(
        lambda v, handler: handler(v), submodel_schema
    )

    model_a_schema = core_schema.model_schema(
        ModelA,
        core_schema.model_fields_schema(
            fields={
                'type': core_schema.model_field(
                    core_schema.with_default_schema(core_schema.literal_schema(['A']), default='A'),
                ),
                'sub': core_schema.model_field(wrapped_submodel_schema),
            },
        ),
    )

    model_b_schema = core_schema.model_schema(
        ModelB,
        core_schema.model_fields_schema(
            fields={
                'type': core_schema.model_field(
                    core_schema.with_default_schema(core_schema.literal_schema(['B']), default='B'),
                ),
                'sub': core_schema.model_field(submodel_schema),
            },
        ),
    )

    for choices in permute_choices([model_a_schema, model_b_schema]):
        schema = core_schema.union_schema(choices)
        validator = SchemaValidator(schema)

        assert isinstance(validator.validate_python({'type': 'A', 'sub': {'x': 'x'}}), ModelA)
        assert isinstance(validator.validate_python({'type': 'B', 'sub': {'x': 'x'}}), ModelB)

        # defaults to leftmost choice if there's a tie
        assert isinstance(validator.validate_python({'sub': {'x': 'x'}}), choices[0]['cls'])

    # test validate_assignment
    class RootModel:
        ab: Union[ModelA, ModelB]

    root_model = core_schema.model_schema(
        RootModel,
        core_schema.model_fields_schema(
            fields={'ab': core_schema.model_field(core_schema.union_schema([model_a_schema, model_b_schema]))}
        ),
    )

    validator = SchemaValidator(root_model)
    m = validator.validate_python({'ab': {'type': 'B', 'sub': {'x': 'x'}}})
    assert isinstance(m, RootModel)
    assert isinstance(m.ab, ModelB)
    assert m.ab.sub.x == 'x'

    m = validator.validate_assignment(m, 'ab', {'sub': {'x': 'y'}})
    assert isinstance(m, RootModel)
    assert isinstance(m.ab, ModelA)
    assert m.ab.sub.x == 'y'
