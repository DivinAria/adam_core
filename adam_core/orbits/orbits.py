import logging
from typing import Optional

import numpy as np
import numpy.typing as npt
import pandas as pd

from ..coordinates.coordinates import Coordinates
from ..coordinates.members import CoordinateMembers

logger = logging.getLogger(__name__)


class Orbits(CoordinateMembers):
    def __init__(
        self,
        coordinates: Coordinates,
        orbit_ids: Optional[npt.ArrayLike] = None,
        object_ids: Optional[npt.ArrayLike] = None,
    ):
        if orbit_ids is not None:
            self._orbit_ids = orbit_ids
        else:
            self._orbit_ids = np.arange(0, len(coordinates))

        if object_ids is not None:
            self._object_ids = object_ids
        else:
            self._object_ids = np.array(["None" for i in range(len(coordinates))])

        super().__init__(
            self,
            coordinates=coordinates,
            cartesian=True,
            keplerian=True,
            spherical=True,
            cometary=True,
        )
        return

    @property
    def orbit_ids(self):
        return self._orbit_ids

    @orbit_ids.setter
    def orbit_ids(self, orbit_ids):
        if len(orbit_ids) != len(self._orbit_ids):
            raise ValueError(
                "Orbit IDs must be the same length as the number of orbits."
            )
        self._orbit_ids = orbit_ids

    @orbit_ids.deleter
    def orbit_ids(self):
        self._orbit_ids = np.arange(0, len(self._orbit_ids))

    @property
    def object_ids(self):
        return self._object_ids

    @object_ids.setter
    def object_ids(self, object_ids):
        if len(object_ids) != len(self._object_ids):
            raise ValueError(
                "Object IDs must be the same length as the number of orbits."
            )
        self._object_ids = object_ids

    @object_ids.deleter
    def object_ids(self):
        self._object_ids = np.array(["None" for i in range(len(self._object_ids))])

    def to_df(
        self,
        time_scale: str = "tdb",
        coordinate_type: Optional[str] = None,
        sigmas: bool = False,
        covariances: bool = False,
    ) -> pd.DataFrame:
        """
        Represent Orbits as a `~pandas.DataFrame`.

        Parameters
        ----------
        time_scale : {"tdb", "tt", "utc"}
            Desired timescale of the output MJDs.
        coordinate_type : {"cartesian", "spherical", "keplerian", "cometary"}
            Desired output representation of the orbits.
        sigmas : bool, optional
            Include 1-sigma uncertainty columns.
        covariances : bool, optional
            Include lower triangular covariance matrix columns.

        Returns
        -------
        df : `~pandas.DataFrame`
            Pandas DataFrame containing orbits.
        """
        df = CoordinateMembers.to_df(
            self,
            time_scale=time_scale,
            coordinate_type=coordinate_type,
            sigmas=sigmas,
            covariances=covariances,
        )
        df.insert(0, "orbit_id", self.orbit_ids)
        df.insert(1, "object_id", self.object_ids)

        return df

    @classmethod
    def from_df(
        cls: "Orbits",
        df: pd.DataFrame,
        coord_cols: Optional[dict] = None,
        origin_col: str = "origin",
        frame_col: str = "frame",
    ) -> "Orbits":
        """
        Read Orbits class from a `~pandas.DataFrame`.

        Parameters
        ----------
        df : `~pandas.DataFrame`
            DataFrame containing orbits.
        coord_cols : dict, optional
            Dictionary containing the coordinate dimensions as keys and their equivalent columns
            as values. If None, this function will use the default dictionaries for each coordinate class.
            The following coordinate (dictionary) keys are supported:
                Cartesian columns: x, y, z, vx, vy, vz
                Keplerian columns: a, e, i, raan, ap, M
                Cometary columns: q, e, i, raan, ap, tp
                Spherical columns: rho, lon, lat, vrho, vlon, vlat
        origin_col : str
            Name of the column containing the origin of each coordinate.
        frame_col : str
            Name of the column containing the coordinate frame.

        Returns
        -------
        cls : `~adam_core.orbits.Orbits`
            Orbits class.
        """
        data = cls._dict_from_df(
            df,
            cartesian=True,
            keplerian=True,
            cometary=True,
            spherical=True,
            coord_cols=coord_cols,
            origin_col=origin_col,
            frame_col=frame_col,
        )

        columns = df.columns.values
        if "orbit_id" in columns:
            data["orbit_ids"] = df["orbit_id"].values
        else:
            data["orbit_ids"] = None

        if "object_id" in columns:
            data["object_ids"] = df["object_id"].values
        else:
            data["object_ids"] = None

        return cls(**data)
