import unittest
from typing import Any, Union, Tuple
from plantimager.commons.RPC import is_instance_of_generic  # Assuming the function is in RPC.py based on project context


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



if __name__ == "__main__":
    unittest.main()