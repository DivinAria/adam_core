# adam_core/observers/tests/testdata

This directory contains .CSVs of containing state vectors of a selection of observatories. These CSVs can be
generated with the following code:

```python
import numpy as np
from astropy.time import Time
from astroquery.jplhorizons import Horizons

from adam_core.coordinates.cartesian import CartesianCoordinates
from adam_core.coordinates.origin import Origin, OriginCodes
from adam_core.coordinates.times import Times

observatory_codes = ["I41", "X05", "F51", "W84", "000", "500"]
times = Time(
    np.arange(59000, 60000, 10),
    format="mjd",
    scale="utc",
)

for code in observatory_codes:
    for id in ["sun", "ssb"]:
        if id == "sun":
            origin = OriginCodes.SUN
        else:
            origin = OriginCodes.SOLAR_SYSTEM_BARYCENTER

        horizons = Horizons(id=id, location=code, epochs={'start':'2013-01-01', 'stop':'2023-01-01', 'step':'10d'})
        result = horizons.vectors(refplane="ecliptic", aberrations="geometric").to_pandas()

        # Flip the signs of the state to get the state of the observer
        states = CartesianCoordinates.from_kwargs(
            times=Times.from_astropy(Time(result["datetime_jd"].values, format="jd", scale="tdb")),
            x=-result["x"].values,
            y=-result["y"].values,
            z=-result["z"].values,
            vx=-result["vx"].values,
            vy=-result["vy"].values,
            vz=-result["vz"].values,
            origin=Origin.from_kwargs(code=[origin.name for _ in range(len(result))]),
            frame="ecliptic"
        )
        states.to_dataframe(covariances=False).to_csv(f"{code}_{id}.csv", index=False)
```
