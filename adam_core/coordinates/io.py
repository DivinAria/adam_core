from typing import TYPE_CHECKING, List, Type, Union

import pandas as pd

from .covariances import CoordinateCovariances
from .frame import Frame
from .origin import Origin
from .times import Times

if TYPE_CHECKING:
    from .cartesian import CartesianCoordinates
    from .cometary import CometaryCoordinates
    from .keplerian import KeplerianCoordinates
    from .spherical import SphericalCoordinates

    CoordinateType = Union[
        CartesianCoordinates,
        CometaryCoordinates,
        KeplerianCoordinates,
        SphericalCoordinates,
    ]


def coords_to_dataframe(
    coords: "CoordinateType",
    coord_names: List[str],
    sigmas: bool = False,
    covariances: bool = False,
) -> pd.DataFrame:
    """
    Store coordinates as a pandas DataFrame.

    Parameters
    ----------
    coords : {CartesianCoordinates, CometaryCoordinates, KeplerianCoordinates, SphericalCoordinates}
        Coordinates to store.
    coord_names : list of str
        Names of the coordinates to store.
    sigmas : bool, optional
        If True, include 1-sigma uncertainties in the DataFrame.
    covariances : bool, optional
        If True, include covariance matrices in the DataFrame. Covariance matrices
        will be split into 21 columns, with the lower triangular elements stored.

    Returns
    -------
    df : `~pandas.Dataframe`
        DataFrame containing coordinates and covariances.
    """
    # Gather times and put them into a dataframe
    df_times = coords.times.to_dataframe(flatten=True)
    times_dict = {col: f"times.{col}" for col in df_times.columns}
    df_times.rename(columns=times_dict, inplace=True)

    df_coords = pd.DataFrame(
        data=coords.values,
        columns=coord_names,
    )

    # Gather the origin and put it into a dataframe
    df_origin = coords.origin.to_dataframe(flatten=True)
    origin_dict = {col: f"origin.{col}" for col in df_origin.columns}
    df_origin.rename(columns=origin_dict, inplace=True)

    # Gather the frame and put it into a dataframe
    df_frame = coords.frame.to_dataframe(flatten=True)
    frame_dict = {col: f"frame.{col}" for col in df_frame.columns}
    df_frame.rename(columns=frame_dict, inplace=True)

    # Gather the covariances and put them into a dataframe
    if covariances or sigmas:
        df_cov = coords.covariances.to_dataframe(
            coord_names=coord_names,
            sigmas=sigmas,
        )
        if not covariances:
            cov_cols = [col for col in df_cov.columns if "cov_" in col]
            df_cov = df_cov.drop(columns=cov_cols)

    # Join the dataframes
    df = df_times.join(df_coords)
    df = df.join(df_origin)
    df = df.join(df_frame)
    if covariances or sigmas:
        df = df.join(df_cov)

    return df


def coords_from_dataframe(
    cls: "Type[CoordinateType]", df: pd.DataFrame, coord_names: List[str]
) -> "CoordinateType":
    """
    Return coordinates from a pandas DataFrame that was generated with
    `~adam_core.coordinates.io.coords_to_dataframe` (or any coordinate type's
    `.to_dataframe` method).

    Parameters
    ----------
    df : `~pandas.Dataframe`
        DataFrame containing coordinates and covariances.
    coord_names : list of str
        Names of the coordinates dimensions.

    Returns
    -------
    coords : {CartesianCoordinates, CometaryCoordinates, KeplerianCoordinates, SphericalCoordinates}
        Coordinates read from the DataFrame.
    """
    times = Times.from_dataframe(
        df[["times.mjd", "times.scale"]].rename(
            columns={"times.mjd": "mjd", "times.scale": "scale"}
        )
    )
    origin = Origin.from_dataframe(
        df[["origin.code"]].rename(columns={"origin.code": "code"})
    )
    frame = Frame.from_dataframe(
        df[["frame.name"]].rename(columns={"frame.name": "name"})
    )
    covariances = CoordinateCovariances.from_dataframe(df, coord_names=coord_names)
    coords = {col: df[col].values for col in coord_names}

    return cls.from_kwargs(
        **coords, times=times, origin=origin, frame=frame, covariances=covariances
    )
