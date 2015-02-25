from __future__ import division

import os,glob
import re

import numpy as np
import astropy.units as u
from astropy.cosmology import FLRW,WMAP9


from .settings import EnvironmentSettings,NGenICSettings
from ..simulations import Gadget2Settings,Gadget2Snapshot,Nicaea 

try:
	from ..extern import _darkenergy,_prefactors
	_darkenergy = _darkenergy
except ImportError:
	_darkenergy = None

name2attr = dict()
name2attr["Om"] = "Om0"
name2attr["Ol"] = "Ode0"
name2attr["w"] = "w0"
name2attr["wa"] = "wa"
name2attr["h"] = "h"
name2attr["Ob"] = "Ob0"
name2attr["si"] = "sigma8"
name2attr["ns"] = "ns"


#####################################################
##############SimulationModel class##################
#####################################################

class SimulationModel(object):

	"""
	Class handler of a weak lensing simulation model, defined by a set of cosmological parameters

	"""

	@classmethod
	def available(cls,environment):

		"""
		Lists all currently available models in the home and storage directories

		:param environment: environment settings of the current machine
		:type environment: EnvironmentSettings

		:returns: list.
		:rtype: SimulationModel

		"""

		models = list()

		#Useful regular expression
		parmatch = re.compile(r"([a-zA-Z]+)([0-9.-]+)")

		if not(os.path.isdir(environment.home)) or not(os.path.isdir(environment.storage)):
			return models

		#Check all available models in the home directory
		dirnames = [ os.path.basename(n) for n in glob.glob(os.path.join(environment.home,"*")) ]

		#Decide which of the directories actually correspond to cosmological models
		for dirname in dirnames:
			
			parameters_dict = dict()
			parameters_list = list()
			parameters = dirname.split("_")
			
			for parameter in parameters:
				
				try:
					par,val = parmatch.match(parameter).groups()
				except TypeError:
					pass
				
				parameters_list.append(par)
				parameters_dict[name2attr[par]] = float(val)

			try:
				cosmoModel = Nicaea(**parameters_dict)
				models.append(cls(cosmology=cosmoModel,environment=environment,parameters=parameters_list))
			except TypeError:
				pass

		#Return the list with the available models
		return models

	def __repr__(self):

		representation_parameters = []
		for p in self.parameters:
			representation_parameters.append("{0}={1:.3f}".format(p,getattr(self.cosmology,name2attr[p])))

		return "<"+ " , ".join(representation_parameters) + ">"

	def __init__(self,cosmology=WMAP9,environment=None,parameters=["Om","Ol","w","ns","si"]):

		"""
		Set the base for the simulation

		:param cosmology: cosmological model to simulate
		:type cosmology: FLRW

		:param environment: environment settings of the current machine
		:type environment: EnvironmentSettings

		:param parameters: cosmological parameters to keep track of
		:type parameters: list.

		"""

		#Safety checks
		assert isinstance(cosmology,FLRW)

		if environment is None:
			self.environment = EnvironmentSettings()
		else:
			assert isinstance(environment,EnvironmentSettings)
			self.environment = environment

		self.cosmology = cosmology
		self.parameters = parameters

		#Define the scaled unit length for convenience
		self.kpc_over_h = u.def_unit("kpc/h",u.kpc/self.cosmology.h)
		self.Mpc_over_h = u.def_unit("Mpc/h",u.Mpc/self.cosmology.h)

		#Build the cosmo_id
		self.cosmo_id = "_".join([ "{0}{1:.3f}".format(p,getattr(self.cosmology,name2attr[p])) for p in parameters if (hasattr(self.cosmology,name2attr[p]) and getattr(self.cosmology,name2attr[p]) is not None)])

		#Create directories accordingly
		self.home_subdir = os.path.join(self.environment.home,self.cosmo_id)
		self.storage_subdir = os.path.join(self.environment.storage,self.cosmo_id)

		for d in [self.home_subdir,self.storage_subdir]:
			if not os.path.isdir(d):
				os.mkdir(d)
				print("[+] {0} created".format(d))


	def newCollection(self,box_size=240.0*u.Mpc,nside=512):

		"""
		Instantiate new simulation with the specified settings

		"""

		newSimulation = SimulationCollection(self.cosmology,self.environment,self.parameters,box_size,nside)

		#Make the corresponding directory if not already present
		for d in [newSimulation.home_subdir,newSimulation.storage_subdir]:
			if not os.path.isdir(d):
				os.mkdir(d)
				print("[+] {0} created".format(d))


		return newSimulation


	@property
	def collections(self):

		"""
		Lists all the available collections for a model

		:returns: list.
		:rtype: SimulationCollection

		"""

		collection_names = [ os.path.basename(d) for d in glob.glob(os.path.join(self.home_subdir,"*")) ]
		collection_list = list()

		for name in collection_names:
			
			try:
				nside,box = name.split("b")
				collection_list.append(SimulationCollection(self.cosmology,self.environment,self.parameters,box_size=float(box)*self.Mpc_over_h,nside=int(nside)))
			except ValueError:
				pass

		return collection_list


##########################################################
##############SimulationCollection class##################
##########################################################

class SimulationCollection(SimulationModel):


	"""
	Class handler of a collection of simulations that share model parameters

	"""

	def __init__(self,cosmology,environment,parameters,box_size,nside):

		super(SimulationCollection,self).__init__(cosmology,environment,parameters)
		self.box_size = box_size
		self.nside = nside

		#Build the geometry_id
		self.geometry_id = "{0}b{1}".format(nside,int(box_size.to(self.Mpc_over_h).value))

		#Build the directory names
		self.home_subdir = os.path.join(self.environment.home,self.cosmo_id,self.geometry_id)
		self.storage_subdir = os.path.join(self.environment.storage,self.cosmo_id,self.geometry_id)


	def __repr__(self):

		return super(SimulationCollection,self).__repr__() + " ; box={0},nside={1}".format(self.box_size,self.nside)


	def newCollection(self):
		raise TypeError("This method should be called on SimulationModel instances!")

	def newInitialCondition(self,seed=0):
		
		#Check if there are already generated initial conditions in there
		ics_present = glob.glob(os.path.join(self.storage_subdir,"ic*"))
		new_ic_index = len(ics_present) + 1

		#Generate the new initial condition
		newIC = SimulationIC(self.cosmology,self.environment,self.parameters,self.box_size,self.nside,new_ic_index,seed)

		#Make dedicated directory for new initial condition
		os.mkdir(newIC.home_subdir)
		print("[+] {0} created".format(newIC.home_subdir))
		os.mkdir(newIC.storage_subdir)
		print("[+] {0} created".format(newIC.storage_subdir))

		#Make new file with the number of the seed
		seedfile = open(os.path.join(newIC.storage_subdir,"seed"+str(seed)),"w")
		seedfile.close()

		return newIC


	@property
	def ics(self):

		"""
		List the available initial conditions (or independent simulations) for the current collection

		:returns: list.
		:rtype: SimulationIC

		"""

		ic_list = list()
		ic_numbers = [ os.path.basename(d).strip("ic") for d in glob.glob(os.path.join(self.storage_subdir,"ic*")) ]

		for ic in ic_numbers:

			seed = int(os.path.basename(glob.glob(os.path.join(self.storage_subdir,"ic"+ic,"seed*"))[0]).strip("seed"))
			ic_list.append(SimulationIC(self.cosmology,self.environment,self.parameters,self.box_size,self.nside,int(ic),seed))

		return ic_list



##########################################################
##############SimulationIC class##########################
##########################################################

class SimulationIC(SimulationCollection):

	"""
	Class handler of a simulation with a defined initial condition

	"""

	def __init__(self,cosmology,environment,parameters,box_size,nside,ic_index,seed):

		super(SimulationIC,self).__init__(cosmology,environment,parameters,box_size,nside)

		#Save random seed information as attribute
		self.ic_index = ic_index
		self.seed = seed

		#Save storage sub-directory name
		self.home_subdir = os.path.join(self.home_subdir,"ic{0}".format(ic_index))
		self.storage_subdir = os.path.join(self.storage_subdir,"ic{0}".format(ic_index))

	def __repr__(self):

		return super(SimulationIC,self).__repr__() + " ; ic={0},seed={1}".format(self.ic_index,self.seed)

	def newInitialCondition(self,seed):
		raise TypeError("This method should be called on SimulationCollection instances!")

	####################################################################################################################################

	def writeNGenIC(self,settings):

		"""
		Generates the parameter file that NGenIC needs to read to generate the current initial condition

		:param settings: NGenIC tunable settings
		:type settings: NGenICSettings

		"""

		if _darkenergy is None:
			raise ImportError("F77 sources in cextern/darkEnergy are not compiled!!")

		#Safety check
		assert isinstance(settings,NGenICSettings)

		#The filename is automatically generated from the class instance
		filename = os.path.join(self.home_subdir,"ngeinc.param")

		#Write the parameter file
		with open(filename,"w") as paramfile:

			#Mesh and grid size
			paramfile.write("Nmesh			{0}\n".format(2*self.nside))
			paramfile.write("Nsample		{0}\n".format(self.nside))

			#Box
			paramfile.write("Box 			{0:.1f}\n".format(self.box_size.to(self.kpc_over_h).value))

			#Base names for outputs
			paramfile.write("Filebase			ics_{0}_ic{1}\n".format(self.cosmo_id,self.ic_index))
			paramfile.write("OutputDir			{0}\n".format(os.path.abspath(self.storage_subdir)))

			#Glass file
			paramfile.write("GlassFile			{0}\n".format(os.path.abspath(settings.GlassFile)))

			#Tiling
			glass = Gadget2Snapshot.open(os.path.abspath(settings.GlassFile))
			nside_glass = glass.header["num_particles_total_side"]
			glass.close()
			paramfile.write("TileFac			{0}\n".format(self.nside//nside_glass))

			#Cosmological parameters
			paramfile.write("Omega			{0:.6f}\n".format(self.cosmology.Om0))
			paramfile.write("OmegaLambda			{0:.6f}\n".format(self.cosmology.Ode0))
			paramfile.write("OmegaBaryon			{0:.6f}\n".format(self.cosmology.Ob0))
			paramfile.write("HubbleParam			{0:.6f}\n".format(self.cosmology.h))
			paramfile.write("w0			{0:.6f}\n".format(self.cosmology.w0))
			paramfile.write("wa			{0:.6f}\n".format(self.cosmology.wa))

			#Initial redshift
			paramfile.write("Redshift 			{0:.6f}\n".format(settings.Redshift))

			#Computation of the prefactors
			OmegaK = 1.0 - self.cosmology.Om0 - self.cosmology.Ode0 - self.cosmology.Onu0
			ret,d1,d2 = _darkenergy.f77main(self.cosmology.h,self.cosmology.Om0,self.cosmology.Onu0,OmegaK,self.cosmology.Ode0,self.cosmology.w0,self.cosmology.wa,0.0,settings.Redshift,settings._zmaxact,settings._zminact,settings._iwmode)
			ret,d1,d2minus = _darkenergy.f77main(self.cosmology.h,self.cosmology.Om0,self.cosmology.Onu0,OmegaK,self.cosmology.Ode0,self.cosmology.w0,self.cosmology.wa,0.0,settings.Redshift-settings._delz,settings._zmaxact,settings._zminact,settings._iwmode)
			vel_prefactor = _prefactors.velocity(settings.Redshift,self.cosmology.Om0,self.cosmology.Ode0,self.cosmology.Onu0,self.cosmology.w0,self.cosmology.wa,self.cosmology.h,d2,d2minus,settings._delz,settings._zmaxact,settings._zminact,settings._iwmode)

			paramfile.write("GrowthFactor			{0:.6f}\n".format(1.0/d2))
			paramfile.write("VelocityPrefactor			{0:.6f}\n".format(vel_prefactor))

			#Sigma8
			paramfile.write("Sigma8				{0:.6f}\n".format(self.cosmology.sigma8))

			#Power Spectrum settings
			paramfile.write("SphereMode			{0}\n".format(settings.SphereMode))
			paramfile.write("WhichSpectrum			{0}\n".format(settings.WhichSpectrum))
			paramfile.write("FileWithInputSpectrum			{0}\n".format(settings.FileWithInputSpectrum))
			paramfile.write("InputSpectrum_UnitLength_in_cm			{0:.6e}\n".format(settings.InputSpectrum_UnitLength_in_cm))
			paramfile.write("ReNormalizeInputSpectrum		{0}\n".format(settings.ReNormalizeInputSpectrum))
			paramfile.write("ShapeGamma			{0:.2f}\n".format(settings.ShapeGamma))
			paramfile.write("PrimordialIndex			{0:.6f}\n".format(settings.PrimordialIndex))

			#Random seed
			paramfile.write("Seed 			{0}\n".format(self.seed))

			#Files written in parallel
			paramfile.write("NumFilesWrittenInParallel			{0}\n".format(settings.NumFilesWrittenInParallel))

			#Units
			paramfile.write("UnitLength_in_cm 			{0:.6e}\n".format(settings.UnitLength_in_cm))
			paramfile.write("UnitMass_in_g			{0:.6e}\n".format(settings.UnitMass_in_g))
			paramfile.write("UnitVelocity_in_cm_per_s 			{0:.6e}\n".format(settings.UnitVelocity_in_cm_per_s))

		#Log and return
		print("[+] NGenIC parameter file {0} written".format(filename))

	####################################################################################################################################

	def writeGadget2(self,settings):

		"""
		Generates the parameter file that Gadget2 needs to read to evolve the current initial condition in time

		:param settings: Gadget2 tunable settings
		:type settings: Gadget2Settings

		"""

		#Safety check
		assert isinstance(settings,Gadget2Settings)

		#The filename is automatically generated from the class instance
		filename = os.path.join(self.home_subdir,"gadget2.param")

		#Write the parameter file
		with open(filename,"w") as paramfile:

			#File names for initial condition and outputs
			initial_condition_file = os.path.join(os.path.abspath(self.storage_subdir),"ics_{0}_ic{1}".format(self.cosmo_id,self.ic_index))
			paramfile.write("InitCondFile			{0}\n".format(initial_condition_file))
			paramfile.write("OutputDir			{0}{1}\n".format(self.storage_subdir,os.path.sep))

			#Use outputs in the settings to write the OutputListFilename, and set this as the output list of the code
			outputs_filename = os.path.join(self.storage_subdir,"outputs.txt")
			np.savetxt(outputs_filename,settings.OutputScaleFactor)
			paramfile.write("OutputListFilename			{0}\n\n".format(os.path.abspath(outputs_filename)))

			#CPU time limit section
			paramfile.write(settings.writeSection("cpu_timings"))

			#Code options section
			paramfile.write(settings.writeSection("code_options"))

			#Initial scale factor time
			ic_filenames = glob.glob(initial_condition_file+"*")

			try:
				ic_snapshot = Gadget2Snapshot.open(ic_filenames[0])
				paramfile.write("TimeBegin			{0}\n".format(ic_snapshot.header["scale_factor"]))
				ic_snapshot.close()
			except IndexError:
				#TODO Dirty,make this better in the future
				paramfile.write("TimeBegin			{0}\n".format(1.0/101.0))

			#Characteristics of run section
			paramfile.write(settings.writeSection("characteristics_of_run"))

			#Cosmological parameters
			paramfile.write("Omega0			{0:.6f}\n".format(self.cosmology.Om0))
			paramfile.write("OmegaLambda			{0:.6f}\n".format(self.cosmology.Ode0))
			paramfile.write("OmegaBaryon			{0:.6f}\n".format(self.cosmology.Ob0))
			paramfile.write("HubbleParam			{0:.6f}\n".format(self.cosmology.h))
			paramfile.write("BoxSize			{0:.6f}\n".format(self.box_size.to(self.kpc_over_h).value))
			paramfile.write("w0			{0:.6f}\n".format(self.cosmology.w0))
			paramfile.write("wa			{0:.6f}\n\n".format(self.cosmology.wa))

			#Output frequency section
			paramfile.write(settings.writeSection("output_frequency"))

			#Accuracy of time integration section
			paramfile.write(settings.writeSection("accuracy_time_integration"))

			#Tree algorithm section
			paramfile.write(settings.writeSection("tree_algorithm"))

			#SPH section
			paramfile.write(settings.writeSection("sph"))

			#Memory allocation section
			paramfile.write(settings.writeSection("memory_allocation"))

			#System of units section
			paramfile.write(settings.writeSection("system_of_units"))

			#Softening lengths section
			paramfile.write(settings.writeSection("softening"))

		#Log and exit
		print("[+] Gadget2 parameter file {0} written".format(filename))






