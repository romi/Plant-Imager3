import unittest
from typing import Any, Union, Tuple
from plantimager.commons.utils import is_instance_of_generic, coerce_to_generic


class TestIsInstanceOfGeneric(unittest.TestCase):
    """Unit tests for the is_instance_of_generic utility function."""

    def test_simple_types(self):
        """Test basic non-generic types."""
        self.assertTrue(is_instance_of_generic(10, int))
        self.assertTrue(is_instance_of_generic("hello", str))
        self.assertFalse(is_instance_of_generic(10, str))

    def test_any_type(self):
        """Test the typing.Any specification."""
        self.assertTrue(is_instance_of_generic([1, 2, 3], Any))
        self.assertTrue(is_instance_of_generic("anything", Any))
        self.assertTrue(is_instance_of_generic(None, Any))

    def test_list_generics(self):
        """Test List generic types with various element types."""
        self.assertTrue(is_instance_of_generic([1, 2, 3], list[int]))
        self.assertTrue(is_instance_of_generic([], list[int]))  # Empty list matches
        self.assertFalse(is_instance_of_generic([1, "2"], list[int]))
        self.assertTrue(is_instance_of_generic(["a", "b"], list[str]))

    def test_dict_generics(self):
        """Test Dict generic types for keys and values."""
        self.assertTrue(is_instance_of_generic({"a": 1, "b": 2}, dict[str, int]))
        self.assertFalse(is_instance_of_generic({"a": "1"}, dict[str, int]))
        self.assertTrue(is_instance_of_generic({}, dict[str, int]))

    def test_fixed_tuple_generics(self):
        """Test fixed-size Tuple generic types."""
        self.assertTrue(is_instance_of_generic((1, "s"), Tuple[int, str]))
        self.assertFalse(is_instance_of_generic((1, 2), Tuple[int, str]))

    def test_variadic_tuple_generics(self):
        """Test variadic Tuple generic types (e.g., Tuple[int, ...])."""
        self.assertTrue(is_instance_of_generic((1, 2, 3), tuple[int, ...]))
        self.assertTrue(is_instance_of_generic((), tuple[int, ...]))
        self.assertFalse(is_instance_of_generic((1, "2"), tuple[int, ...]))

    def test_nested_generics(self):
        """Test nested generic structures like List[List[int]]."""
        complex_data = [[1, 2], [3, 4]]
        self.assertTrue(is_instance_of_generic(complex_data, list[list[int]]))

        invalid_data = [[1, 2], ["3", 4]]
        self.assertFalse(is_instance_of_generic(invalid_data, list[list[int]]))

    def test_union_types(self):
        """Test Union types and the newer | syntax (types.UnionType)."""
        # Testing Union[int, str]
        self.assertTrue(is_instance_of_generic(10, Union[int, str]))
        self.assertTrue(is_instance_of_generic("hi", Union[int, str]))
        self.assertFalse(is_instance_of_generic(1.5, Union[int, str]))

    def test_set_generics(self):
        """Test Set generic types."""
        self.assertTrue(is_instance_of_generic({1, 2, 3}, set[int]))
        self.assertFalse(is_instance_of_generic({1, "2"}, set[int]))

    def test_tuple_of_types(self):
        """Test when generic_type is passed as a tuple of multiple specifications."""
        spec = (list[int], dict[str, int])
        self.assertTrue(is_instance_of_generic([1, 2], spec))
        self.assertTrue(is_instance_of_generic({"a": 1}, spec))
        self.assertFalse(is_instance_of_generic("not in spec", spec))


class TestCoerceToGeneric(unittest.TestCase):

    def test_any_type(self):
        """Should return the value unchanged when generic_type is Any."""
        value = {"a": 1}
        self.assertEqual(coerce_to_generic(value, Any), value)

    def test_simple_type_success(self):
        """Should coerce basic types like int, str, and float."""
        self.assertEqual(coerce_to_generic("123", int), 123)
        self.assertEqual(coerce_to_generic(123, str), "123")
        self.assertEqual(coerce_to_generic(1, float), 1.0)

    def test_simple_type_error(self):
        """Should raise TypeError when simple coercion fails."""
        with self.assertRaises(TypeError):
            coerce_to_generic("abc", int)

    def test_union_types(self):
        """Should try types in a Union until one succeeds."""
        # Using Union[int, str]
        self.assertEqual(coerce_to_generic("10", Union[int, dict]), 10)
        self.assertEqual(coerce_to_generic("10", int | dict), 10)
        self.assertEqual(coerce_to_generic(10, Union[dict, str]), "10")
        self.assertEqual(coerce_to_generic(10, dict | str), "10")

        # Using Python 3.10+ | syntax (simulated via Union for compatibility if needed)
        # In actual 3.10+, this would be int | float
        ComplexUnion = Union[int, float]
        self.assertEqual(coerce_to_generic("1.5", ComplexUnion), 1.5)

    def test_fixed_size_tuple(self):
        """Should coerce each element in a fixed-size tuple."""
        target_type = tuple[int, str, float]
        input_value = ["1", 2, "3.5"]
        expected = (1, "2", 3.5)
        self.assertEqual(coerce_to_generic(input_value, target_type), expected)

    def test_tuple_length_mismatch(self):
        """Should raise TypeError if tuple length doesn't match type definition."""
        with self.assertRaises(TypeError):
            coerce_to_generic([1, 2], tuple[int, int, int])

    def test_variadic_tuple(self):
        """Should coerce all elements to the type specified in a variadic tuple."""
        target_type = tuple[int, ...]
        input_value = ["1", "2", "3"]
        self.assertEqual(coerce_to_generic(input_value, target_type), (1, 2, 3))

    def test_mapping_coercion(self):
        """Should coerce keys and values in a dictionary."""
        target_type = dict[str, int]
        input_value = {1: "10", 2: "20"}
        expected = {"1": 10, "2": 20}
        self.assertEqual(coerce_to_generic(input_value, target_type), expected)

    def test_mapping_type_error(self):
        """Should raise TypeError if input is not a mapping."""
        with self.assertRaises(TypeError):
            coerce_to_generic([1, 2, 3], dict[str, int])

    def test_sequence_coercion(self):
        """Should coerce elements in a list or set."""
        self.assertEqual(coerce_to_generic(["1", "2"], list[int]), [1, 2])
        self.assertEqual(coerce_to_generic([1, "2"], set[int]), {1, 2})

    def test_sequence_invalid_input(self):
        """Should raise TypeError if input is a string but target is a list of characters."""
        # The code explicitly blocks strings/bytes from being treated as iterables for coercion
        with self.assertRaises(TypeError):
            coerce_to_generic("123", list[int])

    def test_nested_structures(self):
        """Should handle deeply nested generic types."""
        target_type = list[dict[str, tuple[int, int]]]
        input_value = ({"coords": ["1", "2"]},)
        expected = [{"coords": (1, 2)}]
        self.assertEqual(coerce_to_generic(input_value, target_type), expected)

    def test_fallback_origin_instantiation(self):
        """Should attempt to call the origin with value if no specific logic matches."""

        # custom class that takes one arg
        class MyBox:
            def __init__(self, val): self.val = val

            def __eq__(self, other): return self.val == other.val

        # This will hit the origin(value) logic
        self.assertEqual(coerce_to_generic(10, MyBox), MyBox(10))

if __name__ == "__main__":
    unittest.main()