import os
import numpy as np
import pandas as pd
import pyvista as pv
from vtk import *
from vtk.util.numpy_support import vtk_to_numpy
from vtk.util.numpy_support import numpy_to_vtk
from lxml import etree as ET
from scipy.interpolate import griddata


class VTUIO(object):
    def __init__(self, filename, dim=3):
        self.filename = filename
        self.reader = vtkXMLUnstructuredGridReader()
        self.reader.SetFileName(self.filename)
        self.reader.Update()
        self.output = self.reader.GetOutput()
        #print("self.output: {}".format(self.output))
        self.pdata = self.output.GetPointData()
        #print("pdata: {}".format(self.pdata))
        self.points = vtk_to_numpy(self.output.GetPoints().GetData())
        self.dim = dim
        if self.dim == 2:
            self.points = np.delete(self.points,2,1)

    def getNeighbors(self, points_interpol, numneighbors=20):
        df = pd.DataFrame(self.points)
        neighbors = {}
        for i, key in enumerate(points_interpol):
            if self.dim == 2:
                df["r_"+str(i)]=(df[0]-points_interpol[key][0])*(df[0]-points_interpol[key][0])+(df[1]-points_interpol[key][1])*(df[1]-points_interpol[key][1])
            else:
                df["r_"+str(i)]=(df[0]-points_interpol[key][0])*(df[0]-points_interpol[key][0])+(df[1]-points_interpol[key][1])*(df[1]-points_interpol[key][1])+(df[2]-points_interpol[key][2])*(df[2]-points_interpol[key][2])
            neighbors[i] = df.sort_values(by=["r_"+str(i)]).head(numneighbors).index
        return neighbors

    def getData(self, neighbors, points_interpol, fieldname):
        field = self.getField(fieldname)
        resp = {}
        for i, key in enumerate(points_interpol):
            if self.dim == 2:
                grid_x, grid_y = np.mgrid[points_interpol[key][0]:(points_interpol[key][0]+0.1):1, points_interpol[key][1]:(points_interpol[key][1]+0.1):1]
                resp[key] = griddata(self.points[neighbors[i]], field[neighbors[i]], (grid_x, grid_y), method='linear')[0][0]
            else:
                grid_x, grid_y, grid_z = np.mgrid[points_interpol[key][0]:(points_interpol[key][0]+0.1):1, points_interpol[key][1]:(points_interpol[key][1]+0.1):1, points_interpol[key][2]:(points_interpol[key][2]+0.1):]
                resp[key] = griddata(self.points[neighbors[i]], field[neighbors[i]], (grid_x, grid_y, grid_z), method='linear')[0][0][0]
        return resp

    def getField(self, fieldname):
        field = vtk_to_numpy(self.pdata.GetArray(fieldname))
        return field

    def getFieldnames(self):
        fieldnames = []
        for i in range(self.pdata.GetNumberOfArrays()):
            fieldnames.append(self.pdata.GetArrayName(i))
        return fieldnames

    def getPointData(self, fieldname, pts = {'pt0': (0.0,0.0,0.0)}):
        resp = {}
        for pt in pts:
            if type(fieldname) is str:
                resp[pt] = []
            elif type(fieldname) is list:
                resp[pt] = {}
                for field in fieldname:
                    resp[pt][field] = []
        nb = self.getNeighbors(pts)
        if type(fieldname) is str:
            data = self.getData(nb, pts, fieldname)
            for pt in pts:
                resp[pt]=data[pt]
        elif type(fieldname) is list:
            data = {}
            for field in fieldname:
                data[field] = self.getData(nb, pts, field)
            for pt in pts:
                for field in fieldname:
                    resp[pt][field]=data[field][pt]
        return resp

    def getPointSetData(self, fieldname, pointsetarray =[(0,0,0)]):
        pts = {}
        # convert into point dictionary
        for i, entry in enumerate(pointsetarray):
            pts['pt'+str(i)] = entry
        resp = self.getPointData(fieldname, pts=pts)
        resp_list = []
        # convert point dictionary into list
        for i, entry in enumerate(pointsetarray):
            resp_list.append(resp['pt'+str(i)])
        resp_array = np.array(resp_list)
        return resp_array


    def writeField(self, field, fieldname, ofilename):
        field_vtk = numpy_to_vtk(field)
        r = self.pdata.AddArray(field_vtk)
        self.pdata.GetArray(r).SetName(fieldname)
        writer = vtkXMLUnstructuredGridWriter()
        writer.SetFileName(ofilename)
        writer.SetInputData(self.output)
        writer.Write()



class PVDIO(object):
    def __init__(self, folder, filename, dim=3):
        self.folder = folder
        self.filename = ""
        self.timesteps = []
        self.vtufilenames = []
        self.readPVD(os.path.join(folder,filename))
        self.dim = dim

    def readPVD(self,filename):
        print(filename)
        self.filename = filename
        tree = ET.parse(self.filename)
        root = tree.getroot()
        for collection in root.getchildren():
            for dataset in collection.getchildren():
                try:
                    self.timesteps.append(float(dataset.attrib['timestep']))
                except:
                    ts = dataset.attrib['timestep'].lower().rstrip().lstrip()
                    if ts.endswith('e'):
                        ts+="0"
                        self.timesteps.append(float(ts))
                    else:
                        print("Could not convert timestep to float")
                        exit()
                self.vtufilenames.append(dataset.attrib['file'])

    def readTimeSeriesSbe(self,fieldname, pts = {'pt0': (0.0,0.0,0.0)}):
        resp_t = {}
        ptsarray = pd.DataFrame(pts).T.values
        for pt in pts:
            if type(fieldname) is str:
                resp_t[pt] = []
            elif type(fieldname) is list:
                resp_t[pt] = {}
                for field in fieldname:
                    resp_t[pt][field] = []
        pc=pv.PolyData(ptsarray)
        #print('pointarray: {}'.format(ptsarray))
        for i, filename in enumerate(self.vtufilenames):
            try:
                mesh=pv.read(os.path.join(self.folder,filename))
                if(fieldname in mesh.cell_arrays.keys()):
                    mesh=mesh.cell_data_to_point_data()
                interpolated = pc.interpolate(mesh)
                if type(fieldname) is str:
                      for j,pt in enumerate(pts):
                            #print("interpolated {} at {}: {}".format(fieldname,pt,interpolated[fieldname]))
                            resp_t[pt].append(interpolated[fieldname][j])       
                elif type(fieldname) is list:
                    data = {}
                    for field in fieldname:
                        data[field] = interpolated[fieldname]
                    for j,pt in enumerate(pts):
                        for field in fieldname:
                            resp_t[pt][field].append(data[field][j])
            except:
                print('Could not read field data')
                continue
        return resp_t
                
    def readTimeSeries(self,fieldname, pts = {'pt0': (0.0,0.0,0.0)}):
        resp_t = {}
        for pt in pts:
            if type(fieldname) is str:
                resp_t[pt] = []
            elif type(fieldname) is list:
                resp_t[pt] = {}
                for field in fieldname:
                    resp_t[pt][field] = []
        for i, filename in enumerate(self.vtufilenames):
            vtu = VTUIO(os.path.join(self.folder,filename), dim=self.dim)
            if i == 0:
                nb = vtu.getNeighbors(pts)
            if type(fieldname) is str:
                data = vtu.getData(nb, pts, fieldname)
                for pt in pts:
                    resp_t[pt].append(data[pt])
            elif type(fieldname) is list:
                data = {}
                for field in fieldname:
                    data[field] = vtu.getData(nb, pts, field)
                for pt in pts:
                    for field in fieldname:
                        resp_t[pt][field].append(data[field][pt])
        return resp_t

    def readTimeStep(self, timestep, fieldname):
        filename = None
        for i, ts in enumerate(self.timesteps):
            if timestep == ts:
                filename = self.vtufilenames[i]
        if not filename is None:
            vtu = VTUIO(filename, dim=self.dim)
            field = vtu.getField(fieldname)
        else:
            filename1 = None
            filename2 = None
            timestep1 = 0.0
            timestep2 = 0.0
            for i, ts in enumerate(self.timesteps):
                try:
                    if (timestep > ts) and (timestep < self.timesteps[i+1]):
                        timestep1 = ts
                        timestep2 = self.timesteps[i+1]
                        filename1 = self.vtufilenames[i]
                        filename2 = self.vtufilenames[i+1]
                except IndexError:
                    print("time step is out of range")
            if (filename1 is None) or (filename2 is None):
                print("time step is out of range")
            else:
                vtu1 = VTUIO(filename1, dim=self.dim)
                vtu2 = VTUIO(filename2, dim=self.dim)
                field1 = vtu1.getField(fieldname)
                field2 = vtu2.getField(fieldname)
                fieldslope = (field2-field1)/(timestep2-timestep1)
                field = field1 + fieldslope * (timestep-timestep1)
        return field

    def readPointSetDataSbe(self, timestep, fieldname, pointa,pointb,resolution=100):
        filename = None
        for i, ts in enumerate(self.timesteps):
            if timestep == ts:
                filename = self.vtufilenames[i]
        if not filename is None:
            mesh=pv.read(os.path.join(self.folder,filename))
            sampled = pv.DataSetFilters.sample_over_line(mesh,pointa, pointb, resolution)
            field = sampled.get_array(fieldname)
            distance = sampled['Distance']
        else:
            filename1 = None
            filename2 = None
            timestep1 = 0.0
            timestep2 = 0.0
            for i, ts in enumerate(self.timesteps):
                try:
                    if (timestep > ts) and (timestep < self.timesteps[i+1]):
                        timestep1 = ts
                        timestep2 = self.timesteps[i+1]
                        filename1 = self.vtufilenames[i]
                        filename2 = self.vtufilenames[i+1]
                except IndexError:
                    print("time step is out of range:{}, {}".format(i,ts))
            if (filename1 is None) or (filename2 is None):
                print("time step is out of range")
            else:
                #print("filename 1: {}".format(filename1))
                #print("filename 2: {}".format(filename2))
                #print("dim {}".format(self.dim))
                mesh1 = pv.read(os.path.join(self.folder,filename1))
                sampled1 = pv.DataSetFilters.sample_over_line(mesh1,pointa, pointb, resolution)
                mesh2 = pv.read(os.path.join(self.folder,filename2))
                sampled2 = pv.DataSetFilters.sample_over_line(mesh2,pointa, pointb, resolution)
                field1 = sampled1.get_array(fieldname)
                field2 = sampled2.get_array(fieldname)
                fieldslope = (field2-field1)/(timestep2-timestep1)
                field = field1 + fieldslope * (timestep-timestep1)
                distance = sampled1['Distance']
        return (field,distance)

    
    def readPointSetData(self, timestep, fieldname, pointsetarray =[(0,0,0)]):
        filename = None
        for i, ts in enumerate(self.timesteps):
            if timestep == ts:
                filename = self.vtufilenames[i]
        if not filename is None:
            vtu = VTUIO(filename, dim=self.dim)
            field = vtu.getPointSetData(fieldname, pointsetarray)
        else:
            filename1 = None
            filename2 = None
            timestep1 = 0.0
            timestep2 = 0.0
            for i, ts in enumerate(self.timesteps):
                try:
                    if (timestep > ts) and (timestep < self.timesteps[i+1]):
                        timestep1 = ts
                        timestep2 = self.timesteps[i+1]
                        filename1 = self.vtufilenames[i]
                        filename2 = self.vtufilenames[i+1]
                except IndexError:
                    print("time step is out of range")
            if (filename1 is None) or (filename2 is None):
                print("time step is out of range")
            else:
                vtu1 = VTUIO(filename1, dim=self.dim)
                vtu2 = VTUIO(filename2, dim=self.dim)
                field1 = vtu1.getPointSetData(fieldname, pointsetarray)
                field2 = vtu2.getPointSetData(fieldname, pointsetarray)
                fieldslope = (field2-field1)/(timestep2-timestep1)
                field = field1 + fieldslope * (timestep-timestep1)
        return field

    def clearPVDrelpath(self):
        xpath="./Collection/DataSet"
        tree = ET.parse(self.filename)
        root = tree.getroot()
        find_xpath = root.findall(xpath)
        for tag in find_xpath:
            filename = tag.get("file")
            filename_new = filename.split("/")[-1]
            tag.set("file", filename_new)
        tree.write(self.filename,
                            encoding="ISO-8859-1",
                            xml_declaration=True,
                            pretty_print=True)
        #update file list:
        newlist = []
        for entry in  self.vtufilenames:
            newlist.append(entry.split("/")[-1])
        self.vtufilenames = newlist

