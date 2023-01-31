import logging
from collections import OrderedDict
from copy import copy, deepcopy
from typing import List, Optional, Union

import numpy as np
import numpy.typing as npt
import pandas as pd
from astropy.time import Time

__all__ = ["Indexable", "concatenate"]

logger = logging.getLogger(__name__)

SLICEABLE_DATA_STRUCTURES = (np.ndarray, np.ma.masked_array, Time)
UNSLICEABLE_DATA_STRUCTURES = (str, int, float, dict, bool, set, OrderedDict)


def _convert_grouped_array_to_slices(values: npt.ArrayLike) -> npt.NDArray[slice]:
    """
    Converts an array of grouped values to a list of slices that select each
    unique value in the array. Sort order doesn't matter.

    Parameters
    ----------
    values : np.ArrayLike
        The values to be converted to slices.

    Returns
    -------
    slices : np.ndarray[slice]
        The slices corresponding to the unique values.

    Raises
    ------
    ValueError: If the values are not grouped.
    """
    # Pandas unique is faster than numpy unique for object dtypes
    # and preserves the order of the unique values by default
    unique_values = pd.unique(values)

    slices = []
    slice_start = 0
    for i in unique_values:
        mask = np.where(values == i)[0]
        if (len(mask) > 1) and np.all(np.diff(mask) != 1):
            raise ValueError("The values must be grouped.")

        slices.append(slice(slice_start, slice_start + len(mask), 1))
        slice_start += len(mask)

    return np.array(slices)


class Indexable:
    """
    Class that enables indexing and slicing of itself and its members.
    If an Indexable subclass has members that are `~numpy.ndarray`s, `~numpy.ma.core.MaskedArray`s,
    lists, or `~astropy.time.core.Time`s then these members are appropriately sliced and
    indexed along their first axis. Any members that are dicts, OrderedDicts, floats,
    integers or strings are not indexed and left unchanged.

    Indexable maintains two array indexes:
        - class: the externally facing index (ie. the index into the class itself)
        - members: the index of the members of the class (ie. the index into
            the data structures carried by the class)


    Class Index:
    [0, 1, 2]
    The class index is used to determine the length (size) of the class. In this example,
    the len(instance) would be 3.

    Class To Members Mapping:
    [0, 0, 0, 1, 1, 1, 2, 2, 2]
    If, as above, the class to members mapping is sorted (monotonically increasing), then
    it is converted to an array of slices which allows for faster querying.
    [slice(0, 2), slice(2, 5), slice(5, 8)]

    Members Index:
    [0, 1, 2, 3, 4, 5, 6, 7, 8]

    For example, here orbits is a subclass of Indexable and has members that are
    `~numpy.ndarray`s, `~numpy.ma.core.MaskedArray`s, and `~astropy.time.core.Time`s.

    ```
    from adam_core.orbits import Orbits
    from adam_core.backend import PYOORB
    from astropy.time import Time
    from astropy import units as u

    # Instantiate an Orbits object with 3 orbits
    t0 = Time([59000.0], scale="utc", format="mjd")
    orbits = Orbits.from_horizons(["Eros", "Ceres", "Duende"], t0)
    len(orbits) == 3

    # If I only wanted one orbit
    single_orbit = orbits[0] # Orbits with one orbit

    # Lets remove the other ones
    del orbits[1:]

    # Lets propagate the orbits to 10 new times
    orbits = Orbits.from_horizons(["Eros", "Ceres", "Duende"], t0)
    t1 = t0 + np.arange(0, 10) * u.day
    backend = PYOORB()
    propagated_orbits = backend.propagate_orbits(orbits, t1)

    # The underlying arrays are now 10 * 3 in length
    len(propagated_orbits) == 30

    # If we update the index to be on orbit_id
    # then the length of the class is 3 even though each
    # member is 10 * 3 in length
    propagated_orbits.set_index("orbit_id")
    len(propagated_orbits) == 3

    # Lets delete all of the states for "Duende"
    del propagated_orbits[2]
    ```
    """

    def __init__(self, index_values: Optional[Union[str, npt.ArrayLike]] = None):
        self.set_index(index_values)
        return

    @property
    def index(self):
        """
        The externally facing index of the class.
        """
        return self._class_index

    @index.setter
    def index(self, value):
        self.set_index(value)

    @index.deleter
    def index(self):
        self.set_index()

    def _check_member_validity(self):
        """
        Scans the class's sliceable members and raises an error if they are
        not all of the same length.

        Returns
        -------
        member_length : int
            The length of the members of the class.
        member_index : `~numpy.ndarray`
            The index of the members of the class.

        Raises
        ------
        ValueError: If the members are not all of the same length.
        """
        # Scan members and if they are of a type that is sliceable
        # then store the length. All sliceable members should have the same length
        # along their first axis.
        member_lengths = {
            len(v)
            for v in self.__dict__.values()
            if isinstance(v, SLICEABLE_DATA_STRUCTURES)
        }
        if len(member_lengths) != 1:
            raise ValueError("All sliceable members must have the same length.")
        member_length = member_lengths.pop()

        member_index = np.arange(0, member_length, dtype=int)

        return member_length, member_index

    def set_index(self, index_values: Optional[Union[str, npt.ArrayLike]] = None):
        """
        Set an index on the class for the given values or attribute name.

        Parameters
        ----------
        index_values : str, np.ArrayLike
            The values to be indexed. If a string is given then the values are taken from the
            attribute of the same name. If an array is given then the values are taken from the
            array itself. If None is given then the index is set to the range of length
            of the class's sliceable members.

        Sets
        ----
        self._class_index : `~numpy.ndarray`
            The externally facing index of the class.
        self._class_index_to_members : `~numpy.ndarray`
            The mapping from the externally facing index to the class members.
        self._class_index_to_members_is_slice : bool
            Whether the mapping from the externally facing index to the class members are slices.
        self._class_index_attribute : str, None
            The attribute on which the index was set, if any. None if no attribute was used.
        self._member_index : `~numpy.ndarray`
            The index of the members of the class.
        self._member_length : int
            The length of the members of the class.


        Raises
        ------
        ValueError: If all sliceable members do not have the same length.
        """
        # Check if all the members are valid: have the same length
        self._member_length, self._member_index = self._check_member_validity()

        # --- Part 2: Figure out the values that are going to be mapped to an index
        # If the values are strings or floats, map their unique values to integers
        # to make future queries faster.

        # If no index values are given then we set the class index
        # to be the range of the member lengths
        if index_values is None:
            # Use the range of the member lengths
            class_index_values = np.arange(0, self._member_length)
            self._class_index_attribute = None
        elif isinstance(index_values, str):
            # Use the provided string as an attribute lookup
            class_index_values = getattr(self, index_values)
            self._class_index_attribute = index_values
        elif isinstance(index_values, np.ndarray):
            # Use the provided values directly
            class_index_values = index_values
            self._class_index_attribute = None
        else:
            raise ValueError("values must be None, str, or numpy.ndarray")

        # If the index is to be set using an array that has a non-integer dtype
        # then we map the unique values of the index to integers. This will make querying the
        # index significantly faster.
        if (
            isinstance(class_index_values, np.ndarray)
            and class_index_values.dtype.type != int
        ):
            logger.debug("Mapping class index values to integers.")
            # We use pandas since numpy unique is slower for object dtypes
            df = pd.DataFrame({"class_index_values": class_index_values})
            df_unique = df.drop_duplicates(keep="first").copy()
            df_unique["class_index_values_mapped"] = np.arange(0, len(df_unique))
            class_index_values = df.merge(
                df_unique, on="class_index_values", how="left"
            )["class_index_values_mapped"].values

        # --- Part 3: Now that we have the values that are going to be mapped to an index
        # we can create the index.

        # Extract unique values to act as the externally facing index.
        self._class_index = pd.unique(class_index_values)

        # See if we can convert the class index to an array of slices.
        try:
            self._class_index_to_members = _convert_grouped_array_to_slices(
                class_index_values
            )
            self._class_index_to_members_is_slice = True
            logger.debug(
                "Class index values are grouped. Converted class index to an array of slices."
            )
        except ValueError:
            self._class_index_to_members = class_index_values
            self._class_index_to_members_is_slice = False
            logger.debug("Class index values are not grouped.")

        return

    def _query_index(
        self, class_ind: Union[int, slice, list, np.ndarray]
    ) -> np.ndarray:
        """
        Given a integer, slice, list, or `~numpy.ndarray`, appropriately slice
        the class index and return the correct index or indices for this class's underlying
        members.

        Parameters
        ----------
        class_ind : Union[int, slice, list, np.ndarray]
            Slice of the class index.

        Returns
        -------
        member_ind : np.ndarray
            Slice into this class's members.
        """
        # --- Integer Slice
        # If the index is an integer then we need to convert it to a slice so that
        # we do not change the dimensionality of the member arrays (or in the cases
        # of a 1D array we need to avoid returning just a single value)
        if isinstance(class_ind, int):

            ind = slice(class_ind, class_ind + 1)

        # --- Slices, Arrays, and Lists
        elif isinstance(class_ind, (slice, np.ndarray, list)):
            ind = class_ind

        else:
            raise TypeError(
                "class_ind should be one of {int, slice, np.ndarray, list}."
            )

        # --- Check boundaries on the slice
        if isinstance(ind, slice) and ind.start is not None and ind.start >= len(self):
            raise IndexError(f"Index {ind.start} is out of bounds.")

        elif isinstance(ind, slice) and self._class_index_to_members_is_slice:

            # Check if the array of slices are consecutive and share
            # the same step size. If so, create a single slice that
            # combines all of the slices.
            slices = self._class_index_to_members[ind]
            is_consecutive = True
            for i, s_i in enumerate(slices[:-1]):
                if s_i.stop != slices[i + 1].start:
                    is_consecutive = False
                    break
                if s_i.step is not None and (s_i.step != slices[i + 1].step):
                    is_consecutive = False
                    break

            if is_consecutive:
                logger.debug(
                    "Slices are consecutive and share the same step. "
                    f"Combining slices a single slice with start {slices[0].start}, "
                    f"end {slices[-1].stop} and step {slices[0].step}."
                )
                return slice(slices[0].start, slices[-1].stop, slices[0].step)
            else:
                logger.debug(
                    "Slices are not consecutive. "
                    "Combining slices a concatenating the members index for each slice."
                )
                return np.concatenate([self._class_index[s] for s in slices])

        elif np.array_equal(self._class_index, self._member_index):
            logger.debug("Using class index to index member arrays.")
            return self._class_index[ind]
        else:
            logger.debug(
                "Using unique class index to index member arrays with np.isin."
            )
            return self._member_index[
                np.isin(
                    self._class_index_to_members,
                    self._class_index[ind],
                )
            ]

    def __len__(self):
        return len(self._class_index)

    def __getitem__(self, class_ind: Union[int, slice, list, np.ndarray]):
        member_ind = self._query_index(class_ind)
        copy_self = copy(self)

        for k, v in copy_self.__dict__.items():
            if k != "_class_index":
                if isinstance(v, (np.ndarray, np.ma.masked_array, Time, Indexable)):
                    copy_self.__dict__[k] = v[member_ind]
                elif isinstance(v, UNSLICEABLE_DATA_STRUCTURES):
                    copy_self.__dict__[k] = v
                elif v is None:
                    pass
                else:
                    err = f"{type(v)} are not supported."
                    raise NotImplementedError(err)
            else:
                copy_self.__dict__[k] = v[np.s_[class_ind]]

        return copy_self

    def __delitem__(self, class_ind: Union[int, slice, tuple, list, np.ndarray]):
        member_ind = self._query_index(class_ind)

        for k, v in self.__dict__.items():
            # Everything but the class index is sliced as normal
            if k != "_class_index":
                if isinstance(v, np.ma.masked_array):
                    self.__dict__[k] = np.delete(v, member_ind, axis=0)
                    self.__dict__[k].mask = np.delete(v.mask, member_ind, axis=0)
                elif isinstance(v, np.ndarray):
                    self.__dict__[k] = np.delete(v, member_ind, axis=0)
                elif isinstance(v, Time):
                    self.__dict__[k] = Time(
                        np.delete(v.mjd, member_ind, axis=0),
                        scale=v.scale,
                        format="mjd",
                    )
                elif isinstance(v, (Indexable)):
                    del v[member_ind]
                elif isinstance(v, UNSLICEABLE_DATA_STRUCTURES):
                    self.__dict__[k] = v
                elif v is None:
                    pass
                else:
                    err = f"{type(v)} are not supported."
                    raise NotImplementedError(err)

            else:
                self.__dict__[k] = np.delete(v, np.s_[class_ind], axis=0)

        self.set_index(self._class_index_attribute)

        return

    def __next__(self):
        try:
            self._class_index[self.idx]
        except IndexError:
            self.idx = 0
            raise StopIteration
        else:
            next = self[self.idx]
            self.idx += 1
            return next

    def __iter__(self):
        self.idx = 0
        return self

    def yield_chunks(self, chunk_size):
        for c in range(0, len(self), chunk_size):
            yield self[c : c + chunk_size]

    def sort_values(
        self,
        by: Union[str, List[str]],
        inplace: bool = False,
        ascending: Union[bool, List[bool]] = True,
    ):
        """
        Sort by values. Values can be contained by this class itself or any attribute
        that is also an Indexable. For example, if an attribute of this class is an Indexable
        with attribute "a", then this function will first search all attributes of this class,
        if no attribute is found then it will search all Indexable attributes of this class
        for the attribute "a".

        Parameters
        ----------
        by : {str, list}
            Sort values using this class attribute or class attributes.
        inplace : bool
            If True will sort the class inplace, if False will return a sorted
            copy of the class.
        ascending : {bool, list}
            Sort columns in ascending order or descending order. If by is a list
            then each attribute can have a separate sort order by passing a list.

        Returns
        -------
        cls : If inplace is False.
        """
        if isinstance(ascending, list) and isinstance(by, list):
            assert len(ascending) == len(by)
            ascending_ = ascending
            by_ = by

        elif isinstance(ascending, bool) and isinstance(by, list):
            ascending_ = [ascending for i in range(len(by))]
            by_ = by

        elif isinstance(ascending, bool) and isinstance(by, str):
            ascending_ = [ascending]
            by_ = [by]

        elif isinstance(ascending, list) and isinstance(by, str):
            ascending_ = ascending
            by_ = [by]

        else:
            pass

        attributes = []
        for by_i in by_:
            # Search this class for the attribute
            # and append it to the list of attributes
            found = False
            try:
                attribute_i = getattr(self, by_i)
                attributes.append(attribute_i)
                found = True

            # If the attribute is not found in this class
            # then search all Indexable attributes for the attribute
            except AttributeError:
                for k, v in self.__dict__.items():
                    if isinstance(v, Indexable):
                        try:
                            attribute_i = getattr(v, by_i)
                            attributes.append(attribute_i)
                            found = True
                        except AttributeError:
                            # Defer assert until the end
                            pass

                if not found:
                    err = f"{by_i} attribute could not be found."
                    raise AttributeError(err)

        data = {}
        for by_i, attribute_i in zip(by_, attributes):
            if isinstance(attribute_i, np.ma.masked_array):
                data[by_i] = deepcopy(attribute_i.filled())
            elif isinstance(attribute_i, Time):
                data[by_i] = deepcopy(attribute_i.mjd)
            else:
                data[by_i] = deepcopy(attribute_i)

        # We use pandas to do sorting because of its built-in support
        # for mixed-type sorting, particularly for strings. np.lexsort
        # requires a little bit more time and effort to get working as
        # well as the pandas sort_values function.
        df = pd.DataFrame(data)
        df_sorted = df.sort_values(
            by=by_,
            ascending=ascending_,
            inplace=False,
            ignore_index=False,
            kind="stable",
        )
        sorted_indices = df_sorted.index.values

        # Store the index attribute if there was one
        index_attribute = deepcopy(self._class_index_attribute)

        # Reset index to be equal to the range of integers corresponding to the
        # length of the class's members.
        self.set_index()

        copy = deepcopy(self[sorted_indices])
        # Reset the index attribute if there was one
        if index_attribute is not None:
            copy.set_index(index_attribute)
            self.set_index(index_attribute)
        else:
            copy.set_index()

        # If inplace is True then update the class's attributes
        # with the sorted attributes. If inplace is False then
        # return the sorted copy.
        if inplace:
            self.__dict__.update(copy.__dict__)
        else:
            return copy
        return


def concatenate(
    indexables: List[Indexable],
) -> "Indexable":
    """
    Concatenate a list of Indexables.

    Parameters
    ----------
    indexables : list
        List of instances of Indexables.

    Returns
    -------
    indexable : Indexable
        Indexable with each sliceable attribute concatenated.
    """
    # Create a deepcopy of the first class in the list
    copy = deepcopy(indexables[0])

    # For each attribute in that class, if it is an array-like object
    # that can be concatenated add it to the dictionary as a list
    # If it is not a data structure that should be concatenated, simply
    # add a copy of that data structure to the list.
    data = {}

    # Astropy time objects concatenate slowly and very poorly so we convert them to
    # numpy arrays and track which attributes should be time objects.
    time_attributes = []
    time_scales = {}
    time_formats = {}
    for k, v in indexables[0].__dict__.items():
        if isinstance(v, (np.ndarray, np.ma.masked_array, Indexable)):
            data[k] = [deepcopy(v)]
        elif isinstance(v, Time):
            time_attributes.append(k)
            time_scales[k] = v.scale
            time_formats[k] = v.format

            data[k] = [v.mjd]

        elif isinstance(v, UNSLICEABLE_DATA_STRUCTURES):
            data[k] = deepcopy(v)
        else:
            data[k] = None

    # Loop through each indexable and add their attributes to lists in data
    # For unsupported data structures insure they are equal
    for indexable_i in indexables[1:]:
        for k, v in indexable_i.__dict__.items():
            if (
                isinstance(v, (np.ndarray, np.ma.masked_array, Indexable))
                and k not in time_attributes
            ):
                data[k].append(v)
            elif k in time_attributes:
                assert time_scales[k] == v.scale
                data[k].append(v.mjd)
            elif isinstance(v, UNSLICEABLE_DATA_STRUCTURES):
                assert data[k] == v
            else:
                pass

    for k, v in data.items():
        if isinstance(v, list):
            if isinstance(v[0], np.ma.masked_array):
                copy.__dict__[k] = np.ma.concatenate(v)
            elif isinstance(v[0], np.ndarray) and k not in time_attributes:
                copy.__dict__[k] = np.concatenate(v)
            elif isinstance(v[0], Indexable):
                copy.__dict__[k] = concatenate(v)
            elif k in time_attributes:
                copy.__dict__[k] = Time(
                    np.concatenate(v), scale=time_scales[k], format="mjd"
                )

    if "_class_index" in copy.__dict__.keys():
        if copy._class_index_attribute is not None:
            copy.set_index(copy._class_index_attribute)
        else:
            copy.set_index()

    return copy
