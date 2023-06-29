import os
from typing import List, Literal

import numpy as np
import spiceypy as sp
from astropy.time import Time
from naif_de440 import de440
from naif_earth_itrf93 import earth_itrf93
from naif_eop_high_prec import eop_high_prec
from naif_eop_historical import eop_historical
from naif_eop_predict import eop_predict
from naif_leapseconds import leapseconds

from ..constants import KM_P_AU, S_P_DAY
from ..coordinates.cartesian import CartesianCoordinates
from ..coordinates.origin import Origin, OriginCodes
from ..coordinates.times import Times

DEFAULT_KERNELS = [
    leapseconds,
    de440,
    eop_predict,
    eop_historical,
    eop_high_prec,
    earth_itrf93,
]


J2000_TDB_JD = 2451545.0


def _jd_tdb_to_et(jd_tdb: np.ndarray) -> np.ndarray:
    """
    Convert an astropy Time object to an ephemeris time (ET) in seconds.

    Parameters
    ----------
    jd_tdb : `~numpy.ndarray` (N)
        Times in JD TDB.

    Returns
    -------
    et : `~numpy.ndarray` (N)
        Times in ET in seconds.
    """
    # Convert to days since J2000 (noon on January 1, 2000)
    days_since_j2000 = jd_tdb - J2000_TDB_JD

    # Convert to seconds since J2000
    # (SPICE format)
    et = days_since_j2000 * S_P_DAY
    return et


def setup_SPICE(kernels: List[str] = DEFAULT_KERNELS, force: bool = False):
    """
    Load SPICE kernels.

    This function checks to see if SPICE has already been initialized for the current process.
    If it has, then it does nothing. If it has not, then it loads the desired kernels into SPICE.
    If force is set to True, then the kernels will be loaded regardless of whether or not SPICE
    has already been initialized. SPICE has a limit on the number of kernels that can be loaded
    at once, so it is recommended to only load the kernels that are needed for the current
    calculation (calling sp.furnsh multiple times will load the same kernel multiple times, which
    will cause an error.)

    Parameters
    ----------
    kernels : list of str
        List of SPICE kernels to load into SPICE.
    """
    process_id = os.getpid()
    env_var = f"ADAM_CORE_SPICE_INITIALIZED_{process_id}"
    if env_var in os.environ and not force:
        return

    for kernel in kernels:
        sp.furnsh(kernel)
    os.environ[env_var] = "True"
    return


def get_perturber_state(
    perturber: OriginCodes,
    times: Time,
    frame: Literal["ecliptic", "equatorial"] = "ecliptic",
    origin: OriginCodes = OriginCodes.SUN,
) -> CartesianCoordinates:
    """
    Query the JPL ephemeris files loaded in SPICE for the state vectors of desired perturbers.

    Parameters
    ----------
    perturber : OriginCodes
        The NAIF ID of the perturber.
    times : `~astropy.time.core.Time` (N)
        Times at which to get state vectors.
    frame : {'equatorial', 'ecliptic'}
        Return perturber state in the equatorial or ecliptic J2000 frames.
    origin :  OriginCodes
        The NAIF ID of the origin.

    Returns
    -------
    states : `~adam_core.coordinates.cartesian.CartesianCoordinates`
        The state vectors of the perturber in the desired frame
        and measured from the desired origin.
    """
    if frame == "ecliptic":
        frame_spice = "ECLIPJ2000"
    elif frame == "equatorial":
        frame_spice = "J2000"
    else:
        err = "frame should be one of {'equatorial', 'ecliptic'}"
        raise ValueError(err)

    # Make sure SPICE is ready to roll
    setup_SPICE()

    # Convert MJD epochs in TDB to ET in TDB
    epochs_tdb = times.tdb.jd
    unique_epochs_tdb = np.unique(epochs_tdb)
    unique_epochs_et = _jd_tdb_to_et(unique_epochs_tdb)

    # Get position of the body in km and km/s in the desired frame and measured from the desired origin
    states = np.empty((len(epochs_tdb), 6), dtype=np.float64)
    for i, epoch in enumerate(unique_epochs_et):
        mask = np.where(epochs_tdb == unique_epochs_tdb[i])[0]
        state, lt = sp.spkez(perturber.value, epoch, frame_spice, "NONE", origin.value)
        states[mask, :] = state

    # Convert to AU and AU per day
    states = states / KM_P_AU
    states[:, 3:] = states[:, 3:] * S_P_DAY

    return CartesianCoordinates.from_kwargs(
        times=Times.from_astropy(times),
        x=states[:, 0],
        y=states[:, 1],
        z=states[:, 2],
        vx=states[:, 3],
        vy=states[:, 4],
        vz=states[:, 5],
        frame=frame,
        origin=Origin.from_kwargs(code=[origin.name for i in range(len(states))]),
    )
