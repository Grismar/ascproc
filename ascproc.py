'''
Copyright 2017 Jaap van der Velde, BMT WBM Pty Ltd.
'''

__version__ = '0.0.1'

import os
import sys
import argparse
import logging
import json
import pyproj
import csv
import time
from dateutil import parser as date_parser


# set up argument parser
argparser = argparse.ArgumentParser(description='Reprocess .asc (ASCII grid) and output as JSON+CSV.')
argparser.add_argument('input', nargs=1,
                       help='.asc input file.')
argparser.add_argument('-o', '--out_file', default='',
                       help='Write output to a specific file (same as input by default, + .json and .csv).')
group = argparser.add_mutually_exclusive_group()
group.add_argument('-ut', '--unix_time', default='',
                       help='UNIX Time to use for a timestamp (default = now).')
group.add_argument('-t', '--iso_time', default='',
                       help='ISO Time to use for a timestamp (default = now).')
argparser.add_argument('-m', '--metadata', default='',
                       help='Seed the metadata with a source file.')
argparser.add_argument('-l', '--log_level', type=int, default=1, choices=range(1, 5), metavar="[1-5]",
                       help='Level of messages to log (1 = error, 2 = warning, 3 = info, 4 = debug) (1 by default).')
argparser.add_argument('-v', '--version', action='version', version='%(prog)s {0}'.format(__version__),
                       help='Number of lines to write to output (1 by default).')
argparser.add_argument('-dn', '--data_name', default='data',
                       help='Specify a name for the data variable other than the default \'data\'.')
argparser.add_argument('-dl', '--data_long', default='data',
                       help='Specify a long (display) name for the data variable other than the default \'data\'.')
argparser.add_argument('-du', '--data_units', default='units',
                       help='Specify units for the data variable other than the default \'unknown\'.')

# parse argument for file names and log level
args = argparser.parse_args(sys.argv[1:])

input_pathname_arg = args.input[0]
output_pathname_arg = args.input[0] if args.out_file == '' else args.out_file

log_levels = {1: logging.ERROR, 2: logging.WARNING, 3: logging.INFO, 4: logging.DEBUG}
logging.basicConfig(level=log_levels[args.log_level], format='%(asctime)s %(message)s')


def process(metadata, input_filename, var_name, var_long, var_units):
    def read_attr(file, type, name):
        s = file.readline()
        attr, value = s.split()
        assert (attr==name), "Expected {0}, but got {1}".format(name, attr)
        return type(value)

    with open(input_filename) as f:
        ncols = read_attr(f,int,'ncols')
        nrows = read_attr(f,int,'nrows')
        xllcorner = read_attr(f, float, 'xllcorner')
        yllcorner = read_attr(f, float, 'yllcorner')
        cellsize = read_attr(f, float, 'cellsize')
        NODATA_value = read_attr(f, float, 'NODATA_value')

        if 'data_epsg' in metadata['global_attributes']:
            p = pyproj.Proj(init="epsg:"+metadata['global_attributes']['data_epsg'])
            ll = p(xllcorner, yllcorner, inverse=True)
            ur = p(xllcorner + ncols * cellsize, yllcorner + nrows * cellsize, inverse=True)
        else:
            ll = (xllcorner, yllcorner)
            ur = (xllcorner + ncols * cellsize, yllcorner + nrows * cellsize)

        metadata['global_attributes']['data_epsg'] = '4326'
        metadata['global_attributes']['data_projection'] = 'WGS 84'
        metadata['global_attributes']['__source'] = os.path.basename(input_filename)

        if not 'variables' in metadata:
            metadata['variables'] = {}
        else:
            var_name = list(metadata['variables'].keys())[0]
            if 'long_name' in metadata['variables'][var_name]:
                var_long = metadata['variables'][var_name]['long_name']
            if 'units' in metadata['variables'][var_name]:
                var_units = metadata['variables'][var_name]['units']

        metadata['variables']['lat'] = {
            'long_name': 'Latitude',
            'units': 'degrees_north',
            'valid_min': ll[1],
            'valid_max': ur[1],
            '__size': [
                ncols
            ]
        }
        metadata['variables']['lon'] = {
            'long_name': 'Longitude',
            'units': 'degrees_east',
            'valid_min': ll[0],
            'valid_max': ur[0],
            '__size': [
                nrows
            ]
        }
        metadata['variables']['start_time'] = {
            'long_name': 'Accumulation start time',
            'standard_name': 'time',
            'units': 'seconds since 1970-01-01 00:00:00',
            '__size': [
                1
            ]
        }
        metadata['variables']['valid_time'] = {
            'long_name': 'Accumulation end time',
            'standard_name': 'time',
            'units': 'seconds since 1970-01-01 00:00:00',
            '__size': [
                1
            ]
        }
        metadata['variables'][var_name] = {
            'long_name': var_long,
            'units': var_units,
            '_FillValue': NODATA_value,
            '__size': [
                ncols,
                nrows
            ]
        }

        line = f.readline()
        data = []
        while (len(data) < nrows) and (line != ''):
            values = []
            while (len(values) < ncols) and (line != ''):
                values = values + line.split()
                if len(values) > ncols:
                    raise Exception("Too many column values {0}, expected {1}".format(len(values), ncols))
                line = f.readline()

            data.append (values)
        if (len(data) != nrows):
            raise Exception("Incorrent number of rows {0}, expected {1}".format(len(data), nrows))

        return metadata, data


try:
    assert (os.path.isfile(input_pathname_arg)), "Input file not found."

    if args.metadata == '':
        metadata_filename = input_pathname_arg+'.json'
    else:
        metadata_filename = args.metadata
        assert(os.path.isfile(metadata_filename)), "Provided metadata filename does not exist."

    if os.path.isfile(metadata_filename):
        with open(metadata_filename, 'r') as f:
            metadata = json.load(f)
    else:
        metadata = {
            'subgroups': {},
            'global_attributes': {},
            'variables': {},
            'data': {}
        }

    if args.unix_time == '':
        if args.iso_time == '':
            timestamp = int(time.time())
        else:
            timestamp = time.mktime(date_parser.parse(args.iso_time).timetuple())
    else:
        timestamp = int(args.unix_time)

    (json_data, csv_data) = process(metadata, input_pathname_arg, args.data_name, args.data_long, args.data_units)

    if not 'data' in metadata:
        metadata['data'] = {}
    metadata['data']['start_time'] = timestamp
    metadata['data']['valid_time'] = timestamp
    metadata['data'][args.data_name] = output_pathname_arg + '.csv'

    def coordinates_to_csv(var, name):
        values = []
        size = var['__size'][0]
        min = var['valid_min']
        delta = (var['valid_max'] - min) / size
        for i in range(0, size):
            values.append(min + i * delta)
        with open(name, 'w') as f:
            writer = csv.writer(f, delimiter=',', lineterminator='\n')
            writer.writerow(values)

    coordinates_to_csv(metadata['variables']['lat'], output_pathname_arg + '.lat.csv')
    coordinates_to_csv(metadata['variables']['lon'], output_pathname_arg + '.lon.csv')

    metadata['data']['lat'] = output_pathname_arg + '.lat.csv'
    metadata['data']['lon'] = output_pathname_arg + '.lon.csv'

    with open(output_pathname_arg+'.json', "w") as f:
        f.write(json.dumps(json_data, indent=4))

    with open(output_pathname_arg + '.csv', 'w') as f:
        writer = csv.writer(f, delimiter=',', lineterminator='\n')
        writer.writerows(csv_data)

except AssertionError as e:
    logging.error('Assertion failed: {0}'.format(str(e)))
except TypeError as e:
    logging.error('Unexpected error: {0}'.format(str(e)))
