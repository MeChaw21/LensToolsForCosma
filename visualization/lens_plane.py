import sys
sys.path.append("..")

from lenstools.simulations import Gadget2Snapshot
import numpy as np
from mayavi import mlab

snap = Gadget2Snapshot.open("Data/gadget/snapshot_001")
plane,res = snap.cutLens(normal=2,center=7.0*snap.Mpc_over_h,thickness=0.5*snap.Mpc_over_h,plane_size=snap.lensMaxSize(),plane_resolution=128,thickness_resolution=8,smooth=2,tomography=True)

scene = mlab.pipeline.volume(mlab.pipeline.scalar_field(plane))