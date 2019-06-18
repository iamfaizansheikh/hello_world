

############################################################################################################################
# Creation date: April 11 2019
# Created by: Hector Gonzalez

# Contained in this version:
# - Baseline removal 
# - Two CFAR 1D for Range and doppler are done
# - Coherent integration across channels should be included
# - Range FFT
# - Doppler FFT
# - Angle FFT is included but for the Single TX case
#	* For the SIngle TX measurements combine: (This is the only microdop measurement we have so far)
#		+ RX2, RX3 and RX4 for elevation
#		+ RX2, RX1 for azimuth
#
# HG Note: Equivalent to V25
# HG Note: FLIPPED means the azimuth direction has the highest number of channels
# HG Note: NOt Flipped means our original setup, where the elevation had the highest number of channels

import matplotlib
import matplotlib.pyplot as plt
from scipy.stats import rayleigh
from matplotlib.colors import BoundaryNorm
from matplotlib.ticker import MaxNLocator
import pylab as P
from scipy.stats import norm
import operator;

import gc # Garbage collector


#import objgraph # Status Memory leak

import numpy as np

from math import ceil

import csv

import pdb
import pickle
import tkinter
from tkinter.filedialog import askopenfilename
from math import cos, sin, radians
from sklearn.cluster import DBSCAN
from sklearn import metrics
from sklearn.datasets.samples_generator import make_blobs
from sklearn.preprocessing import StandardScaler

def csv_writer(data, path):
    """
    Write data to a CSV file path
    """
    #with open(path, "wb") as csv_file:
    with open(path, "w") as csv_file:
        writer = csv.writer(csv_file, delimiter=',')
        for line in data:
            writer.writerow(line)
global data_row
global data_csv # Header

data_csv = ["Frame_i, Target_Number, Range, Doppler, Magnitude_xdTotal".split(",") ]

######## Parameters #########
numADCBits = 16; # number of ADC bits per sample
numADCSamples = 256; # number of ADC samples per chirp
numRx = 4; # number of receivers
chirpSize = numADCSamples*numRx;
numLanes = 2; # do not change. number of lanes is always 2
isReal = 0; # set to 1 if real only data, 0 if complex data0

numFrames = 334;
#numChirps = 128;
numChirps = 64;
# These two are not currently being used because they are too small and the hanning window is becoming only zeros, we are using the nearest power of two which is 8
numVch_az = 2 # Number of channels contributing to the azimuth
numVch_elv = 3 # Number of channels contributing to the elevation

nearest_power_of_two = 8 # NOt the nearest, but a good approximation for the 3DFFT

####### End parameters #######

fc = 77000000000 # 77GHz carrier
c = 300000000 # speed of light
Tchirp = (60)*10**(-6) #for TDM will this be double ??
lambda_mmwave = c/fc
Time_Frame = numChirps*(Tchirp) # 128 chirps of 60 microseconds
vel_resolution = lambda_mmwave/(2*Time_Frame)
#fft_dopplersamples=128
fft_dopplersamples=64
fs=5000000


print("Starting...")

####### Range Doppler function ########
import argparse
import h5py

def detect_peaks(index, x, num_train, num_guard, rate_fa): # x needs to be the range FFT results
    """
    Detect peaks with CFAR algorithm.
    
    num_train: Number of training cells.
    num_guard: Number of guard cells.
    rate_fa: False alarm rate. 
    """
    num_cells = x.size
    num_train_half = round(num_train / 2)
    num_guard_half = round(num_guard / 2)                                                                                                                          
    num_side = num_train_half + num_guard_half
    #if (index == 24):
    
    alpha = num_train*(rate_fa**(-1/num_train) - 1) # threshold factor
    #print("OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO")
    #print("Start CFAR 1D - FUNCTION")
    #print('alpha ',alpha)
    peak_idx = []
    
    y = np.power(np.repeat(10,num_cells),np.divide(x,20))
    threshold = 0
#    for i in range(num_side, num_cells - num_side): # Explore in an interval not starting from zero
#      
#        if i != i-num_side+np.argmax(x[i-num_side:i+num_side+1]): # If i is not equal to the index where the MAX VALUE is in this interval then jump to the next CYCLE
#            continue # Continue jumps to the next cycle without finishing this one, which means what we have below is only made for the else condition
#        #else: # else means we ARE IN A MAXIMUM VALUE within the interval of study
#       
#        # Why are we multiplying by alpha, what is the theory behind it?
#        sum1 = np.sum(x[i-num_side:i+num_side+1])
#        sum2 = np.sum(x[i-num_guard_half:i+num_guard_half+1]) 
#        p_noise = (sum1 - sum2) / num_train # The guard cells are discarded
#        
#        threshold = alpha * p_noise
#        #pdb.set_trace()
#        print('threshold ',threshold)
#        if x[i] > threshold: # Clearly the problem is that the threshold is too high so the max value is not detected
#            peak_idx.append(i)
            
    peak_idy = []
    
    for i in range(num_side, num_cells - num_side): # Explore in an interval not starting from zero
        
        if i != i-num_side+np.argmax(y[i-num_side:i+num_side+1]): # If i is not equal to the index where the MAX VALUE is in this interval then jump to the next CYCLE
            continue # Continue jumps to the next cycle without finishing this one, which means what we have below is only made for the else condition
        #else: # else means we ARE IN A MAXIMUM VALUE within the interval of study
       
        # Why are we multiplying by alpha, what is the theory behind it?
        sum1 = np.sum(y[i-num_side:i+num_side+1])
        sum2 = np.sum(y[i-num_guard_half:i+num_guard_half+1]) 
        p_noise = (sum1 - sum2) / num_train # The guard cells are discarded

        threshold = alpha * p_noise
        #print('threshold ',threshold)
        if y[i] > threshold: # Clearly the problem is that the threshold is too high so the max value is not detected
            peak_idy.append(i)
    
    #peak_idx = np.array(peak_idx, dtype=int)
    peak_idy = np.array(peak_idy, dtype=int)
    
    #pdb.set_trace()
    del x, y, threshold, num_cells, num_train_half, num_guard_half, num_side
    gc.collect() # All the previous delete get collected here
    #print("OOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOOO")    
    return peak_idy

def range_doppler_No_CFAR(data, Frame_selected, chirps=64,#chirps=128, # 128 = one Tx case, 64 = 2 Tx case
                  samples=256,
                  fft_rangesamples=256, # nfft_r = 2^nextpow2(size(xrv,1));
#                  fft_dopplersamples=128, # nfft_d = 2^nextpow2(size(xrv,3));
                  fft_dopplersamples=64, # nfft_d = 2^nextpow2(size(xrv,3));
                  fs=5000000,
                  kf=29.9817*(10**12),
                  min_range=0.083384197,
                  max_range=25.0152593):
    """
    Computes a range-doppler map for a given number of chirps and samples per chirp.
    :param data: FMCW radar data frame consisting of <chirps>x<samples>
    :param chirps: Number of chirps (Np)
    :param samples: Number of samples (N)
    :param fft_rangesamples: Number of samples for the range fft.
    :param fft_dopplersamples: Number of samples for the doppler fft.
    :param fs: Constant depending on the radar recording parameters.
    :param kf: Constant depending on the radar recording parameters. Slope of the FMCW Ramp
    :param min_range: Minimum value to take into account for the range axis in the range-doppler map. delta_r = c/(2BW) -> BW = T_sweep * slope = 60*29.9817*(10**6) -> delta_r = 300000000/(2*1798902000) = 0.083384197693927
    :param max_range: Maximum value to take into account for the range axifc = 77000000000 # 77GHz carrier
    s in the range-doppler map. d_max = Fsc/2S Slope S -> d_max = 5000000*300000000/(2*29.9817*(10**12))
    :return: Returns a 2D dimensional range-doppler map representing the reflected power over all range-doppler bins.
    """

    # HG NOte: IT needs to return the range fft output only for plotting outside

    data = data.reshape(chirps, samples).T
    Ny, Nx = data.shape  # rows (N), columns (Np)

    window = np.hanning(Ny)
    scaled = np.sum(window)
    window2d = np.tile(window, (Nx, 1)).T
    data = data * window2d

    # Calculate Range FFT
    x = np.empty([fft_rangesamples, Nx], dtype = np.complex64)
    start_index = int((fft_rangesamples - Ny) / 2)
    x[start_index:start_index + Ny, :] = data
    X = np.fft.fft(x, fft_rangesamples, 0) / scaled * (2.0 / 2048)
    #pdb.set_trace()
    print("")
    print("RANGE DOPPLER MAP - MODULE")
    print("")

    auxlongitud = fft_rangesamples // 2

    X = X[0:fft_rangesamples // 2, :] # Floor division
    #print("Shape of X after extracting negatives: ", X.shape) # The shape is 128 including the zero
    #print("Number of frequencies to explore: ", fft_rangesamples // 2)
    #longitud_window = 20 # Used for the threshold. To astimate an average in the threshold
    #print("fft_rangesamples // = ", fft_rangesamples // 2)

    # Chirp ID for loop must go here
    ######## Fit data to a PDF
    longitudNEGseries = fft_rangesamples // 2
    print("LOGITUD NEG SERIES ", longitudNEGseries)

    # Extract range. But this is over the indexes. Nothing to do with the amplitude
    _freq = np.arange(fft_rangesamples // 2) / float(fft_rangesamples) * fs
    _range = _freq * 3e8 / (2 * kf) # kf is the slope of the FMCW ramp
    min_index = np.argmin(np.abs(_range - min_range))
    max_index = np.argmin(np.abs(_range - max_range))

    X = X[min_index: max_index, :] # This is where we take the amplitudes already fixed

    Ny, Nx = X.shape

    # Extract Static Baseline
    sizes_loops = X.shape
    baseline_all = np.mean(X[:, :])    
    print("baseline_all",baseline_all)
    for chirp_idx in range(sizes_loops[0]):
        for samples_idx in range(sizes_loops[1]):
            X[chirp_idx, samples_idx] = X[chirp_idx, samples_idx] - baseline_all

    X_range_fft = X
    window = np.hanning(Nx)
    scaled = np.sum(window)
    window2d = np.tile(window, (Ny, 1))
    X = X * window2d

    rd = np.zeros((Ny, fft_dopplersamples), dtype='complex_')
    start_index = int((fft_dopplersamples - Nx) / 2)
    rd[:, start_index:start_index + Nx] = X

    range_doppler = np.fft.fft(rd, fft_dopplersamples, 1) / scaled
    range_doppler = np.fft.fftshift(range_doppler, axes=1)

    range_doppler_complex = range_doppler # The range_doppler_complex matrix will be used for the angle of arrival
    #pdb.set_trace()
    range_doppler = np.abs(range_doppler)
    range_doppler = 20 * np.log10(range_doppler)

    del X, rd, window, scaled, window2d, data # neg_noise_series_avg, pos_noise_series_avg, 	

    gc.collect() # All the previous delete get collected here # VOLVER ACA

    return range_doppler_complex, range_doppler, X_range_fft # Returns the range_doppler and the X_range_fft, which the last will be used only for plotting


###### Function to convert RAW to adc_databin
def adcRAW2adcBIN(fileName, numADCBits, numADCSamples, numRx, chirpSize, numLanes, isReal, numFrames, numChirps):
    retVal = np.empty([numADCSamples*numChirps*numFrames, numRx], dtype = np.complex64) # Should contain all the adcData. In reality it should be complex 16 Re and 16 Im
    LVDS = np.empty([numADCSamples*numChirps*numFrames*numRx], dtype = np.complex64) # The length of the LVDS corresponds to filesize/2 in matlab, and filesize/4 in python because Python interprets a byte as single unit, while matlab does it for every two bytes

    # During the streaming, these values are unknown, how long does it take, the number of frames or any of it, we have to let it run

    with open("adc_data_Raw_0.bin", "rb") as f:

        # Capture headerfc = 77000000000 # 77GHz carrier

        # We initially assume the file comes okay with header.
        header_byte1 = f.read(1) # This is taking only 8 bits. Byte
        header_byte2 = f.read(1) # This is taking only 8 bits. Byte
        header_byte3 = f.read(1) # This is taking only 8 bits. Byte
        header_byte4 = f.read(1) # This is taking only 8 bits. Byte

        counter_packet = int.from_bytes(header_byte4+header_byte3+header_byte2+header_byte1, byteorder='big', signed=True) # Convert to integer
        print('counter packet: ', counter_packet)
        
        #if counter_packet==15192:
            #pdb.set_trace()

        header_byte5 = f.read(1) # This is taking only 8 bits. Byte
        header_byte6 = f.read(1) # This is taking only 8 bits. Byte
        header_byte7 = f.read(1) # This is taking only 8 bits. Byte
        header_byte8 = f.read(1) # This is taking only 8 bits. Byte

        length_packet = int.from_bytes(header_byte8+header_byte7+header_byte6+header_byte5, byteorder='big', signed=True) # Convert to integer
        print('Length Of Current Packet: ', length_packet)

        header_byte9 = f.read(1) # This is taking only 8 bits. Byte
        header_byte10 = f.read(1) # This is taking only 8 bits. Byte
        header_byte11 = f.read(1) # This is taking only 8 bits. Byte
        header_byte12 = f.read(1) # This is taking only 8 bits. Byte
        header_byte13 = f.read(1) # This is taking only 8 bits. Byte
        header_byte14 = f.read(1) # This is taking only 8 bits. Byte

        packet_history = int.from_bytes(header_byte14+header_byte13+header_byte12+header_byte11+header_byte10+header_byte9, byteorder='big', signed=True) # Convert to integer
        print('Number of packets transmitted in the previous packets without including this one: ', packet_history)


        LSB_Re_1 = f.read(1) # This is taking only 8 bits. Bytes. Convert from byte
        MSB_Re_1 = f.read(1) # This is taking only 8 bits. Bytes. Two consecutive bytes are composing one number. The last being the MSB

        LSB_Re_2 = f.read(1)
        MSB_Re_2 = f.read(1)

        LSB_Im_1 = f.read(1)
        MSB_Im_1 = f.read(1)

        LSB_Im_2 = f.read(1)
        MSB_Im_2 = f.read(1)

        counter_bytes = 22 # 14 + 8 bytes
        counter = 0
        counter_bytes_for_header = counter_bytes


        # The header is repeated every 1456 bytes
        # In 334 frames there are 120269 complete packets
        # and one incomplete packet that it has 528 bytes
        # For a total of 120269*1456 + 528 = 175112192
        # Which corresponds to 334 frames ×128 chirps ×4 channels ×256 samples ×4 bytes

        # We can estimate then the amount of packets that we expect and inform if we lost some.

        while MSB_Im_2: # As long as the last one has something, the rest surely do
            # Do stuff
            # First Number
            Re_1_byte = MSB_Re_1+LSB_Re_1 # Concatenate bytes
            Im_1_byte = MSB_Im_1+LSB_Im_1 # Concatenate bytes

            # Second number
            Re_2_byte = MSB_Re_2+LSB_Re_2 # Concatenate bytes
            Im_2_byte = MSB_Im_2+LSB_Im_2 # Concatenate bytes

            # First Number
            Re_1 = int.from_bytes(Re_1_byte, byteorder='big', signed=True) # Convert to integer
            Im_1 = int.from_bytes(Im_1_byte, byteorder='big', signed=True) # Convert to Integer

            # Second number
            Re_2 = int.from_bytes(Re_2_byte, byteorder='big', signed=True) # Convert to integer
            Im_2 = int.from_bytes(Im_2_byte, byteorder='big', signed=True) # Convert to integer

            #if(Re_1==0 and Im_1==0 and Re_2==0 and Im_2==0):
                #pdb.set_trace()

            LVDS[counter] = Re_1 + Im_1*1j
            LVDS[counter+1] = Re_2 + Im_2*1j

            counter = counter + 2;

            # Capture the next group
            LSB_Re_1 = f.read(1) # This is taking only 8 bits. Bytes. Convert from byte
            MSB_Re_1 = f.read(1) # This is taking only 8 bits. Bytes. Two consecutive bytes are composing one number. The last being the MSB

            LSB_Re_2 = f.read(1)
            MSB_Re_2 = f.read(1)

            LSB_Im_1 = f.read(1)
            MSB_Im_1 = f.read(1)

            LSB_Im_2 = f.read(1)
            MSB_Im_2 = f.read(1)

            counter_bytes = counter_bytes + 8
            counter_bytes_for_header = counter_bytes_for_header + 8

            # Capture header
            if (counter_bytes_for_header == 1470): # Not the last one will be captured. Actually I think it will also be captured because you reach the header first.
                header_byte1 = f.read(1) # This is taking only 8 bits. Byte
                header_byte2 = f.read(1) # This is taking only 8 bits. Byte
                header_byte3 = f.read(1) # This is taking only 8 bits. Byte
                header_byte4 = f.read(1) # This is taking only 8 bits. Byte
                header_byte5 = f.read(1) # This is taking only 8 bits. Byte
                header_byte6 = f.read(1) # This is taking only 8 bits. Byte
                header_byte7 = f.read(1) # This is taking only 8 bits. Byte
                header_byte8 = f.read(1) # This is taking only 8 bits. Byte
                header_byte9 = f.read(1) # This is taking only 8 bits. Byte
                header_byte10 = f.read(1) # This is taking only 8 bits. Byte
                header_byte11 = f.read(1) # This is taking only 8 bits. Byte
                header_byte12 = f.read(1) # This is taking only 8 bits. Byte
                header_byte13 = f.read(1) # This is taking only 8 bits. Byte
                header_byte14 = f.read(1) # This is taking only 8 bits. Byte
                counter_bytes = counter_bytes + 14
                counter_bytes_for_header = 14

                counter_packet = int.from_bytes(header_byte4+header_byte3+header_byte2+header_byte1, byteorder='big', signed=True) # Convert to integer
                print('counter packet: ', counter_packet)
#                if counter_packet==15192:
#                    pdb.set_trace()
                length_packet = int.from_bytes(header_byte8+header_byte7+header_byte6+header_byte5, byteorder='big', signed=True) # Convert to integer
                print('Length Of Current Packet: ', length_packet)
                packet_history = int.from_bytes(header_byte14+header_byte13+header_byte12+header_byte11+header_byte10+header_byte9, byteorder='big', signed=True) # Convert to integer
                print('Number of packets transmitted in the previous packets without including this one: ', packet_history)


        # Once we are done we will have all the info in LVDS
        #pdb.set_trace()
        print('Shape of LVDS after the capture of all values: ', LVDS.shape)
        print('Example for LVDS(1): ', LVDS[1]) # This is not the first element, the first element is the zero element
        print('Example for LVDS(2): ', LVDS[2])

        LVDS = np.reshape(LVDS, (numChirps*numFrames, numADCSamples*numRx))
        #LVDS = np.reshape(LVDS, (numADCSamples*numRx, numChirps*numFrames))

        #LVDS = np.transpose(LVDS) # We had to transpose in matlab, but here it was already in its CORRECT FORM
        print('Shape of LVDS after the RESHAPE to [numADCSamples*numRx numChirps]: ', LVDS.shape)

        # Next step is to pass LVDS to adcData
        # The data is organized in columns of chirps, and we need to translate that into adcData
        adcData = np.empty([numRx, numChirps*numFrames*numADCSamples], dtype = np.complex64)

        #print('LVDS Data Final: ', LVDS[0:50]) # We shouldnt transpose here
        #pdb.set_trace()
        for row in range(numRx):
            for i in range(numChirps*numFrames): # Total number of chirps in all Frames

                adcData[row, (i)*numADCSamples:(i+1)*numADCSamples] = LVDS[i, (row)*numADCSamples:(row+1)*numADCSamples]


        retVal = adcData

        del adcData, LVDS
        gc.collect()

        return retVal



# Starting...
# The expected length of bytes is 334*4*128*256*4 = 175112192 bytes in total
# In samples we should have 43778048, which is dividing by 4 the previous one, as 4 bytes conform a single sample
### Printing expected:
## counter packet:  120269
## Length Of Current Packet:  1456
## Number of packets transmitted in the previous packets without including this one:  175110208
## counter packet:  120270
## Length Of Current Packet:  528
## Number of packets transmitted in the previous packets without including this one:  175111664
## Shape of LVDS after the capture of all values:  (43778048,)
## Example for LVDS(1):  (9+68j)
## Example for LVDS(2):  (7+68j)
## Shape of LVDS after the RESHAPE to [numADCSamples*numRx numChirps]:  (42752, 1024)
#### Use this to compare if the 334 frames were received correctly

#fileName = "D:\Masters NES\Masters Thesis\Work Folder\Dataset_Faizan\Running\09_Single_Crossing9m_Chen_5m_s\adc_data_Raw_0.bin";


#tkinter.Tk().withdraw() # Close the root window
fileName = askopenfilename()

#pdb.set_trace()
retVal = adcRAW2adcBIN(fileName, numADCBits, numADCSamples, numRx, chirpSize, numLanes, isReal, numFrames, numChirps) # retVal should be the structure with all the complex values
# Here we are supposed to have all the information from the files
# f_add
#np.savetxt('/test.out', retVal, delimiter=',')
#newretVal = np.loadtxt('example.txt',unpack= True)
#newretVal = np.split(newretVal,2)[0] + 1j *(np.split(newretVal,2)[1])
#newretVal = newretVal.reshape(4, 10944512)
#retVal = np.transpose(newretVal)
#end f_add
retVal = np.transpose(retVal)
#  print('retVal[0:50,:]',retVal[0:132,:])

# We also need to redefine the multiple target peaks

line_Samples_Ch1 = retVal[:,0]
line_Samples_Ch2 = retVal[:,1]
line_Samples_Ch3 = retVal[:,2]
line_Samples_Ch4 = retVal[:,3]

#print('line_Samples_Ch1[0:50,:]',line_Samples_Ch1[0:132])
#pdb.set_trace()
line_Samples_Ch1      = np.reshape(line_Samples_Ch1, (numFrames,numChirps,numADCSamples))
line_Samples_Ch11 = line_Samples_Ch1[:,0::2,:]
line_Samples_Ch12  = line_Samples_Ch1[:,1::2,:]

line_Samples_Ch2      = np.reshape(line_Samples_Ch2, (numFrames,numChirps,numADCSamples))
line_Samples_Ch21 = line_Samples_Ch2[:,0::2,:]
line_Samples_Ch22  = line_Samples_Ch2[:,1::2,:]

line_Samples_Ch3      = np.reshape(line_Samples_Ch3, (numFrames,numChirps,numADCSamples))
line_Samples_Ch31 = line_Samples_Ch3[:,0::2,:]
line_Samples_Ch32  = line_Samples_Ch3[:,1::2,:]

line_Samples_Ch4      = np.reshape(line_Samples_Ch4, (numFrames,numChirps,numADCSamples)) # (8, 128, 256)
line_Samples_Ch41 = line_Samples_Ch4[:,0::2,:]
line_Samples_Ch42  = line_Samples_Ch4[:,1::2,:]


print('Reshaped line_Samples_Ch1', line_Samples_Ch1.shape)
print('Reshaped line_Samples_Ch2', line_Samples_Ch2.shape)
print('Reshaped line_Samples_Ch3', line_Samples_Ch3.shape)
print('Reshaped line_Samples_Ch4', line_Samples_Ch4.shape)

def argmax2d(X):
            n, m = X.shape
            x_ = np.ravel(X)
            k = np.argmax(x_)
            i, j = k // m, k % m
            del X, x_, k, n, m
            gc.collect()
            return i, j


from operator import add
fft_rangesamples=256 # nfft_r = 2^nextpow2(size(xrv,1));
#fft_dopplersamples=128 # nfft_d = 2^nextpow2(size(xrv,3));
fft_dopplersamples=64 # nfft_d = 2^nextpow2(size(xrv,3));

# Loop for Frames
sizes_loops = line_Samples_Ch1.shape

TWOFrames = 2
Frame_selected = 32
#for Frame_selected in range(TWOFrames):
while Frame_selected < 35:
#for Frame_selected in range(numFrames):
        Frame_selected = Frame_selected + 1    
        ## REMOVE BASELINE - MARZO 21 2019
        print('Frame selected: ', Frame_selected)
        #pdb.set_trace()
        #Frame_selected = 0 # Iterate here if you want to take all frames
#        rd1_complex, rd1, X_range_fft1 = range_doppler_No_CFAR(line_Samples_Ch1[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
#        rd2_complex, rd2, X_range_fft2 = range_doppler_No_CFAR(line_Samples_Ch2[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
#        rd3_complex, rd3, X_range_fft3 = range_doppler_No_CFAR(line_Samples_Ch3[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
#        rd4_complex, rd4, X_range_fft4 = range_doppler_No_CFAR(line_Samples_Ch4[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        
        rd1_complex1, rd11, X_range_fft11 = range_doppler_No_CFAR(line_Samples_Ch11[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        rd2_complex1, rd21, X_range_fft21 = range_doppler_No_CFAR(line_Samples_Ch21[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        rd3_complex1, rd31, X_range_fft31 = range_doppler_No_CFAR(line_Samples_Ch31[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        rd4_complex1, rd41, X_range_fft41 = range_doppler_No_CFAR(line_Samples_Ch41[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        
        rd1_complex2, rd12, X_range_fft12 = range_doppler_No_CFAR(line_Samples_Ch12[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        rd2_complex2, rd22, X_range_fft22 = range_doppler_No_CFAR(line_Samples_Ch22[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        rd3_complex2, rd32, X_range_fft32 = range_doppler_No_CFAR(line_Samples_Ch32[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        rd4_complex2, rd42, X_range_fft42 = range_doppler_No_CFAR(line_Samples_Ch42[Frame_selected, :, :], Frame_selected) # Data being passed is 256 x 128
        # Shape is 508 range bins and 256 doppler bins
        #pdb.set_trace()
        ######### START - COHERENT INTEGRATION ACROSS CHANNELS FOR PLOTTING PURPOSES ONLY

#        X_abs_rd1 = abs(X_range_fft1)
#        X_rd1 = 20 * np.log10(X_abs_rd1)
#
#        X_abs_rd2 = abs(X_range_fft2)
#        X_rd2 = 20 * np.log10(X_abs_rd2)
#
#        X_abs_rd3 = abs(X_range_fft3)
#        X_rd3 = 20 * np.log10(X_abs_rd3)
#
#        X_abs_rd4 = abs(X_range_fft4)
#        X_rd4 = 20 * np.log10(X_abs_rd4)
#        
#        #X_rd_total = list( map(add, X_abs_rd1, X_abs_rd2, X_abs_rd3, X_abs_rd4) )
#        X_rd_partial = list( map(add, X_rd1, X_rd2) )        
#        X_rd_partial2 = list( map(add, X_rd_partial, X_rd3) )        
#        X_rd_total = list( map(add, X_rd_partial2, X_rd4) )
        
        
        X_abs_rd11 = abs(X_range_fft11)
        X_rd11 = 20 * np.log10(X_abs_rd11)

        X_abs_rd21 = abs(X_range_fft21)
        X_rd21 = 20 * np.log10(X_abs_rd21)

        X_abs_rd31 = abs(X_range_fft31)
        X_rd31 = 20 * np.log10(X_abs_rd31)

        X_abs_rd41 = abs(X_range_fft41)
        X_rd41 = 20 * np.log10(X_abs_rd41)
        
        #X_rd_total = list( map(add, X_abs_rd1, X_abs_rd2, X_abs_rd3, X_abs_rd4) )
        X_rd_partial1 = list( map(add, X_rd11, X_rd21) )        
        X_rd_partial21 = list( map(add, X_rd_partial1, X_rd31) )        
        X_rd_total1 = list( map(add, X_rd_partial21, X_rd41) )
        
        
        X_abs_rd12 = abs(X_range_fft12)
        X_rd12 = 20 * np.log10(X_abs_rd12)

        X_abs_rd22 = abs(X_range_fft22)
        X_rd22 = 20 * np.log10(X_abs_rd22)

        X_abs_rd32 = abs(X_range_fft32)
        X_rd32 = 20 * np.log10(X_abs_rd32)

        X_abs_rd42 = abs(X_range_fft42)
        X_rd42 = 20 * np.log10(X_abs_rd42)
        
        #X_rd_total = list( map(add, X_abs_rd1, X_abs_rd2, X_abs_rd3, X_abs_rd4) )
        X_rd_partial2 = list( map(add, X_rd12, X_rd22) )        
        X_rd_partial22 = list( map(add, X_rd_partial2, X_rd32) )        
        X_rd_total2 = list( map(add, X_rd_partial22, X_rd42) )
        
        
        X_rd_total = list( map(add, X_rd_total2, X_rd_total1))
        #pdb.set_trace()
        print("len(X_rd_total)", len(X_rd_total))
        print("len(X_rd_total[0])", len(X_rd_total[0]))

        #del X_rd_partial, X_rd_partial2, X_abs_rd1, X_abs_rd2, X_abs_rd3, X_abs_rd4, X_rd1, X_rd2, X_rd3, X_rd4, X_range_fft1, X_range_fft2, X_range_fft3, X_range_fft4          
        del X_rd_partial1, X_rd_partial21, X_abs_rd11, X_abs_rd21, X_abs_rd31, X_abs_rd41, X_rd11, X_rd21, X_rd31, X_rd41, X_range_fft11, X_range_fft21, X_range_fft31, X_range_fft41          
        del X_rd_partial2, X_rd_partial22, X_abs_rd12, X_abs_rd22, X_abs_rd32, X_abs_rd42, X_rd12, X_rd22, X_rd32, X_rd42, X_range_fft12, X_range_fft22, X_range_fft32, X_range_fft42          

        # Find max peaks in range for each chirp - First CFAR 1D
        #longitudNEGseries = fft_rangesamples // 2
        range_size_total = len(X_rd_total)
        dop_size_total = len(X_rd_total[0]) # Continuar aca para la nueva CFAR function

        X_rd_total_np = np.array(X_rd_total)        

        print("X_rd_total_np.shape", X_rd_total_np.shape)


        peak_idx_list_range_only = []  
        list_aux = []
        for dop_id in range(dop_size_total):
                ####### Apply 1D CFAR Here
                ## CFAR
                #false_alarm_rate = 0.25
                false_alarm_rate = 0.00001
                #print("dop_id",dop_id)
                #if (dop_id == 24):
                #pdb.set_trace()
                #peak_idx = detect_peaks(X_rd_total_np[:,dop_id], num_train=10, num_guard=2, rate_fa=false_alarm_rate) # Number of training cells, Number of cells guarding the true value, false alarm rate
                peak_idx = detect_peaks(dop_id, X_rd_total_np[:,dop_id], num_train=10, num_guard=2, rate_fa=false_alarm_rate) # Number of training cells, Number of cells guarding the true value, false alarm rate
                list_aux = peak_idx.tolist()
                peak_idx_list_range_only.append(peak_idx)
                # LOOP FOR EACH POSITIVE FREQUENCY IN THE RANGE FFT
                for rangeFreq_idx in range(range_size_total):        
                        if rangeFreq_idx in peak_idx: # Then it means it is a maximum so don't mark it
                                continue # Continue jumps to the next cycle because we don't need to mark this value
                        else: # Entering the else means it was not detected as peak in the CFAR, so we assign it to the lowest value we have in the complete X_rd1
                                X_rd_total_np[rangeFreq_idx,dop_id] = -520 # Before we were assigning -130 but, because we are adding the four channels, then that value becomes among the smallest
                # END LOOP FOR EACH POSITIVE FREQUENCY IN THE RANGE FFT
        # End LOOP dop_id 
        #pdb.set_trace()
        clean_peak_idx_list_range = []
        for aux_idx_list in range(len(peak_idx_list_range_only)): # 
                        for aux_idx_units in range(len(peak_idx_list_range_only[aux_idx_list])):
                                                clean_peak_idx_list_range.append(peak_idx_list_range_only[aux_idx_list][aux_idx_units])
        clean_peak_idx_list_range = list( dict.fromkeys(clean_peak_idx_list_range) ) # Removes duplicates
        # End of First CFAR 1D
        #pdb.set_trace()
        # PLot
      
        
        max_rang_index, max_dop_index = X_rd_total_np.shape
        max_range=25.0152593
        axis_range = np.linspace(0, max_range, num=max_rang_index)
        axis_doppler = np.linspace(0, fft_dopplersamples, num=max_dop_index)
      
        fig1 = P.figure();
        fig1colormesh = P.pcolormesh(axis_doppler, axis_range, X_rd_total_np, edgecolors='None')
        fig1.colorbar(fig1colormesh)
        fig1title = P.title('Range vs Chirps - Sum ALl Channels');
        fig1xlabel = P.xlabel('Chirps ');
        fig1ylabel = P.ylabel('Range (meters)');
        string_aux = 'RangeVersus'+'chirps_Frame_'+str(Frame_selected)+'_AllCh'

        name_string = string_aux + '.png'

        fig1.savefig(name_string, bbox_inches='tight') # Good we are saving the picture of the doppler map
        fig1.clf()
        P.clf()
        P.gcf().clear()
        P.close('all')

        del fig1, fig1colormesh, fig1title, fig1xlabel, fig1ylabel, peak_idx_list_range_only
        ######### FINISH - COHERENT INTEGRATION ACROSS CHANNELS FOR PLOTTING PURPOSES ONLY

        ######### START - INCLUDE HERE THE SUM OF RANGE DOPPLER MAPS PLUS THE NEW CFAR MODULE
#        rd_partial = list( map(add, rd1, rd2) )        
#        rd_partial2 = list( map(add, rd_partial, rd3) )        
#        rd_total_list = list( map(add, rd_partial2, rd4) ) 
#        rd_total = np.array(rd_total_list)
#        del rd_partial1, rd_partial21, rd_total_list1
        
        rd_partial1 = list( map(add, rd11, rd21) )        
        rd_partial21 = list( map(add, rd_partial1, rd31) )        
        rd_total_list1 = list( map(add, rd_partial21, rd41) ) 
        
        rd_partial2 = list( map(add, rd12, rd22) )        
        rd_partial22 = list( map(add, rd_partial2, rd32) )        
        rd_total_list2 = list( map(add, rd_partial22, rd42) ) 

        rd_total_list = list( map(add, rd_total_list1, rd_total_list2) ) 

        rd_total = np.array(rd_total_list)
        
        
        del rd_partial1, rd_partial21, rd_total_list1, rd_partial2, rd_partial22, rd_total_list2  

        #clean_peak_idx_list_range # Contains the range peaks

        # Start - Second 1D CFAR

        range_size, dop_size = rd_total.shape # Continuar aca para la nueva CFAR function
        print('Shape of rd_total.shape: ', rd_total.shape)
        print("")
        print('Size of rd_total.size: ', rd_total.size)
        print("")
        #### LOOP FOR SELECTED RANGE BINS

        # ONly these will be exposed to the ANgle FFT
        list_of_targets = []
        pair_of_coordinates = [] # range_id, dopFreq_idx
     
        for range_id in range(range_size): # Only those elements with peak in range    - SECOND CFAR (detect_peaks)
                false_alarm_rate = 0.00001
                peak_dop_idx = detect_peaks(range_id, rd_total[range_id,:], num_train=10, num_guard=2, rate_fa=false_alarm_rate) # Number of training cells, Number of cells guarding the value, false alarm rate
                # Besides being in the peak_dop_idx, there should be something to relate the pairs and the magnitude
                for doppFreq_idx in range(dop_size):
                        if (range_id in clean_peak_idx_list_range) and (doppFreq_idx in peak_dop_idx): # and (rd_total[range_id,doppFreq_idx]>-185): # Then it means it is a maximum so don't mark it # It doesn't mean they are pairs
                                pair_of_coordinates = [range_id,doppFreq_idx] # Restart them at every iteration
                                list_of_targets.append(pair_of_coordinates) # April 10 2019. One error here cis that we are saving the range with all the possible clean doppler indices. WRONG.
                                continue # Continue jumps to the next cycle because we don't need to mark this value
                        else: # Entering the else means it was not detected as peak in the CFAR
                                rd_total[range_id,doppFreq_idx] = -520 # It is true that we leave some of them out, but we are still passing a lot of garbage

                # END LOOP FOR EACH DOPPLER BIN
        #### END LOOP FOR RANGE BINS


        #pdb.set_trace()
        # How many targets did we capture:
        print("List of targets: len(list_of_targets)", len(list_of_targets))

        if len(list_of_targets) == 0:
            continue
        #DBSCAN
#        db = DBSCAN(eps=2, min_samples=2).fit(list_of_targets)
#        core_samples_mask = np.zeros_like(db.labels_, dtype=bool)
#        core_samples_mask[db.core_sample_indices_] = True
#        labels = db.labels_      
#        # Number of clusters in labels, ignoring noise if present.
#        n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)
#        n_noise_ = list(labels).count(-1)
        
        
        #pdb.set_trace()
        #print("How does it look like one target: list_of_targets[3]", list_of_targets[3])
        #list_of_objects # We should have here a list of objects         # We will use the list of objects for the ANgle of arrival and the plot of range and chirps
        # End - Second 1D CFAR

        #### START - PLOT THE COHERENT INTEGRATION OF THE RANGE DOPPLER MAP BELOW
        max_rang_index, max_dop_index = rd_total.shape
        print("max_rang_index is ", max_rang_index) # HG: Why is the resolution 126?
        print("max_dop_index is ", max_dop_index)

        range_index, dop_index = argmax2d(rd_total) # Correct
        print('')
        print('Finding the maximum value')
        print('Range and dop indexes: range_index, dop_index = ', range_index, dop_index)
        print('Range (Meters) should be = ', 0.083384197*range_index)
        vel_index = dop_index - fft_dopplersamples/2 # 128/2=> 64 ---> dop_index - 64. For instance, if it is 60, then we have -4, which is correct
        print('Velocity (Meters/sec) should be = ', vel_resolution*vel_index) # Velocity_resolution = lambda/(2Time_Frame) // Time_chirp = 128chirps*60*10^(-6)
        max_range=25.0152593
        axis_range = np.linspace(0, max_range, num=max_rang_index)
        axis_doppler = np.linspace((-fft_dopplersamples/2)*vel_resolution, (fft_dopplersamples/2)*vel_resolution, num=max_dop_index)
        # PRINT DOPPLER MAP.
        # uncomment start
        print('rd_total shape: ',rd_total.shape)
        fig3 = P.figure();
       
        fig3colormesh = P.pcolormesh(axis_doppler, axis_range, rd_total, edgecolors='None')
        
        #P.plt.gca().invert_yaxis()
        #P.matshow(dbv(trunc_image));
        fig3.colorbar(fig3colormesh)
        #P.clim([-125,-85])
        fig3title = P.title('Range Doppler Map');
        fig3xlabel = P.xlabel('Velocities (m/s)');
        fig3ylabel = P.ylabel('Range (meters)');
        string_aux = 'RangeDopplerMap_Frame_'+str(Frame_selected)+'_Total'
        name_string = string_aux + '.png'
        fig3.savefig(name_string, bbox_inches='tight') 

        fig3.clf()
        P.clf()
        P.gcf().clear()
        P.close('all')
        del fig3, fig3colormesh, fig3title, fig3xlabel, fig3ylabel
        del pair_of_coordinates, list_aux, peak_idx, clean_peak_idx_list_range # Don't delete yet rd1, rd2, rd3 and rd4 because we need them for the angle of arrival
        #### END-  PLOT THE COHERENT INTEGRATION OF THE RANGE DOPPLER MAP BELOW

        ########## END - INCLUDE HERE THE SUM OF RANGE DOPPLER MAPS PLUS THE NEW CFAR MODULE


        ########## START ANGLE OF ARRIVAL
        # APRIL 3 2019: 5:10 PM
        # Analyze the shape of rd1, rd2, rd3, rd4
        # Extract the rows that we are interested in, which are marked by list_of_targets
        #num_angle_bins_output = 1024 # THeoretically this is actually the number of channels, but if we add 1024, the output will be padded
        num_angle_bins_output = 8 #numVch_az 

        NFFTAnt_Az = num_angle_bins_output;	#FFR length for azimuth
        NFFTAnt_Elv = num_angle_bins_output;	#FFR length for azimuth

        output_3d_fft_Az = 0.00001*np.ones([num_angle_bins_output,max_rang_index]) # (num_angles, range_bins) # We will fill it up with only the output of the FFt
        output_3d_fft_Elv = 0.00001*np.ones([num_angle_bins_output,max_rang_index]) # (num_angles, range_bins) # We will fill it up with only the output of the FFt
        # Organize Elevation structure
        #		+ RX2, RX3 and RX4 for elevation: 	rd2, rd3, rd4
        #		+ RX2, RX1 for azimuth: rd2, rd1, 
        
        #input_3d_fft_Az = np.empty([numVch_az, len(list_of_targets)]) # The direction of the targets is the axis=0 direction
        #input_3d_fft_Elv = np.empty([numVch_elv, len(list_of_targets)]) # The direction of the targets is the axis=0 direction
        #nearest_power_of_two = 8        
        input_3d_fft_Az = np.zeros([nearest_power_of_two, len(list_of_targets)],dtype=complex) # We need it to be zero because the elements without physical antenna will be automatically zero padded
        input_3d_fft_Elv = np.zeros([nearest_power_of_two, len(list_of_targets)]) 

        #print("list of targets COMPLETE: ", list_of_targets)
	        	# New configuration: All the experiments after APril 19.
        
        # Organize Azimuth structure
        for aux in range(len(list_of_targets)): # ITerate across each target

	        	# New configuration: All the experiments after APril 19.
	        	# New configuration: All the experiments after APril 19.
	        	# New configuration: All the experiments after APril 19.
	        	#input_3d_fft_Elv[0,aux] = rd2_complex[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 2 - Coordinates range,doppler
	        	#input_3d_fft_Elv[1,aux] = rd1_complex[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 1

        		# Elevation: Places the contribution in the middle of the array to leave the rest as zero padded
	        	#input_3d_fft_Az[0,aux] = rd2_complex[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 2
 	        	#input_3d_fft_Az[2,aux] = rd4_complex[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 4
	        	#input_3d_fft_Az[1,aux] = rd3_complex[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 3

	        	# OLd configuration: Previous experiments
                #input_3d_fft_Az[0,aux] = rd2_complex[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 2 - Coordinates range,doppler
                #input_3d_fft_Az[1,aux] = rd1_complex[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 1
                pdb.set_trace()
                v = ((-fft_dopplersamples/2) + (list_of_targets[aux][1]-1))*vel_resolution                
                phi = -(4*(np.pi)*v*Tchirp)/(lambda_mmwave)
                 #this phase has to be subtracted for compensation
                 
                 
                input_3d_fft_Az[0,aux] = rd2_complex1[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 2 - Coordinates range,doppler
                input_3d_fft_Az[1,aux] = rd1_complex1[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 1  
                pdb.set_trace();
                
            
                phase_correcton = complex(cos(phi),sin(phi)) #this has to be multiplied to the data received from the second transmitter
                
                input_3d_fft_Az[2,aux] = (rd2_complex2[list_of_targets[aux][0],list_of_targets[aux][1]])*phase_correcton # Channel 2 - Coordinates range,doppler
                input_3d_fft_Az[3,aux] = rd1_complex2[list_of_targets[aux][0],list_of_targets[aux][1]]*phase_correcton # Channel 1
	       
                
                
        		# Elevation: Places the contribution in the middle of the array to leave the rest as zero padded
                input_3d_fft_Elv[0,aux] = rd2_complex1[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 2
                input_3d_fft_Elv[1,aux] = rd3_complex1[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 3
                input_3d_fft_Elv[2,aux] = rd4_complex1[list_of_targets[aux][0],list_of_targets[aux][1]] # Channel 4


	        	# The conditional of 1 to 7 m/s and -7 to -1 m/s helps to constraint only to the microdoppler signature
	        	# We shouldn't include the targets with -520 or -540, and neglect all those with magnitude smaller than -185 and range greater than 2.2 for this specifical case, but we can't generalize, the range condition is not a good idea for the code
                if(axis_doppler[list_of_targets[aux][1]] > 1 and axis_doppler[list_of_targets[aux][1]] < 7) or (axis_doppler[list_of_targets[aux][1]] < -1 and axis_doppler[list_of_targets[aux][1]] > -7):
        	        	# We enter here only when the velocities qualify for being microdoppler signature
        	        	#final_string = str(Frame_selected)+","+str(aux)+","+str(axis_range[list_of_targets[aux][0]])+","+str(axis_doppler[list_of_targets[aux][1]])+","+str(X_rd_total_np[list_of_targets[aux][0],list_of_targets[aux][1]])
        	        	final_string = str(Frame_selected)+","+str(aux)+","+str(axis_range[list_of_targets[aux][0]])+","+str(axis_doppler[list_of_targets[aux][1]])+","+str(rd_total[list_of_targets[aux][0],list_of_targets[aux][1]]) # It can't be X_rd_total because this is the output of the range FFT, chirps do not mean anything here with this indices

	                	data_row = final_string
	                	data_csv.append(data_row.split(",")) # Is rd_total complex??? Do we have to extract the magnitude?? It's not complex. The angle of arrival will take the complex and we will continue using rd_total to extract the magnitude to the csv.


		
        ########## END ANGLE OF ARRIVAL

        print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")
        print("Angle of Arrival")
        print("^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^")
        print("input_3d_fft_Az.shape", input_3d_fft_Az.shape)
        print("input_3d_fft_Elv.shape", input_3d_fft_Elv.shape)
        print("")
        print("input_3d_fft_Az[:,0]", input_3d_fft_Az[:,0])
        print("input_3d_fft_Elv[:,0]", input_3d_fft_Elv[:,0])
        
        # Windowing function
        # input_3d_fft_Az.shape  => 	numVch_az  x len(list_of_targets) 
        # WinAnt2D_Az.shape 	 => 	len(list_of_targets) x numVch_Az

        # Shape of input_3d_fft_Elv => numVch_elv x len(list_of_targets)
        # WinAnt2D_Elv.shape 	 => 	len(list_of_targets) x numVch_Elv



        # Azimuth
        WinAnt_Az = np.hanning(nearest_power_of_two);
        ScaWinAnt_Az = np.sum(WinAnt_Az);

        WinAnt2D_Az = np.tile(WinAnt_Az, (len(list_of_targets), 1));		#        WinAnt2D_Az = np.tile(WinAnt_Az, (np.size(vRangeExt), 1));
        JOpt_s = np.multiply(input_3d_fft_Az, np.transpose(WinAnt2D_Az)); # Windowing function to input_3d_fft_Az



        # IMPORTANT NOTE: We have confirmed the zero padding action on the fft and it add zeros only at the end


        JOpt_f = np.fft.fft(JOpt_s, NFFTAnt_Az, 0) / ScaWinAnt_Az;

        #JOpt_f = fft(JOpt_s, NFFTAnt_Az, 0) / ScaWinAnt_Az;
        JOpt = np.fft.fftshift(JOpt_f, 0);

        # Elevation
        WinAnt_Elv = np.hanning(nearest_power_of_two);
        ScaWinAnt_Elv = np.sum(WinAnt_Elv);

        WinAnt2D_Elv = np.tile(WinAnt_Elv, (len(list_of_targets), 1));		#        WinAnt2D_Az = np.tile(WinAnt_Az, (np.size(vRangeExt), 1));
        JOpt_s_Elv = np.multiply(input_3d_fft_Elv, np.transpose(WinAnt2D_Elv)); # Windowing function to input_3d_fft_Az
        JOpt_f_Elv = np.fft.fft(JOpt_s_Elv, NFFTAnt_Elv, 0) / ScaWinAnt_Elv;
        JOpt_Elv = np.fft.fftshift(JOpt_f_Elv, 0);

        print("")
        contador_updates_output3dfft = 0;
        # Defining Range grid
        kf_slope = 29.9817*(10**12) #(fStop - fStrt) / TRampUp;
        vRange = [i for i in range(max_rang_index)];
        vRange = np.divide(vRange, max_rang_index / (fs * c / (2 * kf_slope)));#range bins
        
        # Put the targets information back in a complete matrix with the original shape output_3d_fft_Az
        list_of_targets_Angles = []
        list_of_targets_Angles_Elv = []

        for index_targets in range(len(list_of_targets)): # For each angle and range, check if there is a target there
        	        	# ONe of the things that might be happening is that we are saying that there is only one angle per target, which is kind of true :D        	        	
        	        	list_of_targets_Angles.append(np.argmax(abs(JOpt[:,index_targets]))) # Store the angle index where we have the maximum for this target
        	        	list_of_targets_Angles_Elv.append(np.argmax(abs(JOpt_Elv[:,index_targets])))
        print("")

        # NOw we put those angles into all the grids for range and angles
        for index_targets in range(len(list_of_targets)):	
         	            for aux in range(max_rang_index): # ITerate over the range grid
         	            	if (aux == list_of_targets[index_targets][0]): # aux is the index # We do have a response from the Angle FFT because we did it only for those
                	        	contador_updates_output3dfft = contador_updates_output3dfft + 1        
                	        	output_3d_fft_Az[list_of_targets_Angles[index_targets]][aux] =  abs(JOpt[list_of_targets_Angles[index_targets]][index_targets]) 
                	        	output_3d_fft_Elv[list_of_targets_Angles_Elv[index_targets]][aux] =  abs(JOpt_Elv[list_of_targets_Angles_Elv[index_targets]][index_targets]) 
                	        	continue        # Whatever its not filled here, just leave it as zero
        #pdb.set_trace()
        
        #from math import cos, radians
        
        #list_of_targets_Positions = [(r0*cosA0,r0*sinA0), ....542 elements... (r542*cosA542,r542*sinA542)]
        #rindex = list_of_targets[index][0]
        #Aindex = JOpt[list_of_targets_Angles[index]][index]
        #JOpt[list_of_targets_Angles[1]][1]
        list_of_targets_Positions =[]
        for index in range(len(list_of_targets)):
            list_of_targets_Positions.append([abs(vRange[list_of_targets[index][0]]*sin(radians(np.angle(JOpt[list_of_targets_Angles[index]][index])))),
                                              vRange[list_of_targets[index][0]]*cos(radians(np.angle(JOpt[list_of_targets_Angles[index]][index])))])
        
        
        
        for index in range(len(list_of_targets)):
            print(vRange[list_of_targets[index][0]])
                 
    
    
        db = DBSCAN(eps=0.5, min_samples=2).fit(list_of_targets_Positions)
        core_samples_mask = np.zeros_like(db.labels_, dtype=bool)
        core_samples_mask[db.core_sample_indices_] = True
        labels = db.labels_      
        # Number of clusters in labels, ignoring noise if present.
        n_clusters_ = len(set(labels)) - (1 if -1 in labels else 0)
        n_noise_ = list(labels).count(-1)
        
        #pdb.set_trace()
               
        print("")
        print("list_of_targets_Angles_Az", list_of_targets_Angles)
        print("list_of_targets_Angles_Elv", list_of_targets_Angles_Elv)
        print("")

        print("Azimuth")
        #print("Abs(JOpt).shape",JOpt.shape)
        #print("Abs(JOpt) = output_3d_fft_Az",output_3d_fft_Az)
        #print("np.min(Abs(JOpt) = output_3d_fft_Az)",np.min(output_3d_fft_Az))
        #print("np.max(Abs(JOpt) = output_3d_fft_Az)",np.max(output_3d_fft_Az))
        JdB = 20.*np.log10(output_3d_fft_Az);
        JMax = np.max(JdB);
        JNorm = JdB - JMax;
        JNorm[JNorm < -60.] = -60.; # Lowest value is -60

        print("Elevation")
        JdB_Elv = 20.*np.log10(output_3d_fft_Elv);
        JMax_Elv = np.max(JdB_Elv);
        JNorm_Elv = JdB_Elv - JMax_Elv;
        JNorm_Elv[JNorm_Elv < -60.] = -60.; # Lowest value is -60

        print("")
        # Range - Azimuth Polar Plot
        fig30 = plt.figure(30, figsize=(9, 9));
        # Positions for polar plot of cost function
        # Defining angle grid
        lower_interval = int(-NFFTAnt_Az / 2) # From -512 
        upper_interval = int(NFFTAnt_Az / 2) # to 511 should be done
        vAngDeg = [np.float(i) for i in range(lower_interval, upper_interval)]; # This is allowed in python3.6
        vAngDeg = np.multiply(np.arcsin(np.divide(vAngDeg, NFFTAnt_Az / 2)), 180.0 / np.pi);
        vU = vAngDeg * np.pi/180.;

        vRangeExt = vRange # Pass the complete Range grid

        mU, mRange = np.meshgrid(vU, vRangeExt); # vRangeExt is the range grid

        ax = fig30.add_subplot(111, projection='polar');
        ax.pcolormesh(mU, mRange, np.transpose(JNorm));
        string_aux = 'AzimuthPolarPlot_Frame_'+str(Frame_selected)+'_Total'
        name_string = string_aux + '.png'
        #fig30.savefig(name_string, bbox_inches='tight') 
        fig30.clf()
        #ax.clf()
        P.clf()
        P.gcf().clear()
        P.close('all')

        # Range - Elevation Polar Plot
        fig40 = plt.figure(40, figsize=(9, 9));
        # Positions for polar plot of cost function
        # Defining angle grid
        lower_interval_Elv = int(-NFFTAnt_Elv / 2) # From -512 
        upper_interval_Elv = int(NFFTAnt_Elv / 2) # to 511 should be done
        vAngDeg_Elv = [np.float(i) for i in range(lower_interval_Elv, upper_interval_Elv)]; # This is allowed in python3.6
        vAngDeg_Elv = np.multiply(np.arcsin(np.divide(vAngDeg_Elv, NFFTAnt_Elv / 2)), 180.0 / np.pi);
        vU_Elv = vAngDeg_Elv * np.pi/180.;

        vRangeExt = vRange # Pass the complete Range grid

        mU_Elv, mRange = np.meshgrid(vU_Elv, vRangeExt); # vRangeExt is the range grid

        ax_Elv = fig40.add_subplot(111, projection='polar');
        ax_Elv.pcolormesh(mU_Elv, mRange, np.transpose(JNorm_Elv));
        string_aux = 'ElevationPolarPlot_Frame_'+str(Frame_selected)+'_Total'
        name_string = string_aux + '.png'
        #fig40.savefig(name_string, bbox_inches='tight') 
        fig40.clf()
        #ax.clf()
        P.clf()
        P.gcf().clear()
        P.close('all')

        ###### AZIMUTH - Compare MUSIC and DBF #####
        fig50 = plt.figure(50, figsize=(9, 9));
        print("")        
        print("Plot DBF")        
        print("JOpt.shape", JOpt.shape)        # 8 channels x 605 targets
        print("vAngDeg", vAngDeg)        # 8 channels x 605 targets
        print("")        
        #JOpt_min = np.min(np.log10(np.sum(np.abs(JOpt), 1))); 
        #JOpt_max = np.max(np.log10(np.sum(np.abs(JOpt), 1)));


        
        print("np.sum(np.abs(output_3d_fft_Az), 1)",np.sum(np.abs(output_3d_fft_Az), 1))
        print("np.log10(np.sum(np.abs(output_3d_fft_Az), 1))",np.log10(np.sum(np.abs(output_3d_fft_Az), 1)))

        JOpt_min = np.min(np.log10(np.sum(np.abs(output_3d_fft_Az), 1))); 
        JOpt_max = np.max(np.log10(np.sum(np.abs(output_3d_fft_Az), 1)));

        print("JOpt_min", JOpt_min)
        print("JOpt_max", JOpt_max)
        print("JOpt.shape",JOpt.shape)


        print("vAngDeg", vAngDeg)
        print("JOpt.shape", JOpt.shape)
        print("output_3d_fft_Az.shape", output_3d_fft_Az.shape)
        #print("output_3d_fft_Az.shape", output_3d_fft_Az.shape)
        yaxis = -(JOpt_min - np.log10(np.sum(np.abs(output_3d_fft_Az), 1)))/(JOpt_max - JOpt_min)
        #yaxis = -(JOpt_min - np.log10(np.sum(np.abs(JOpt), 1)))/(JOpt_max - JOpt_min)

        print("yaxis.shape",yaxis.shape)
        print("yaxis",yaxis)

        plt.plot(vAngDeg, -(JOpt_min - np.log10(np.sum(np.abs(output_3d_fft_Az), 1)))/(JOpt_max - JOpt_min));#DBF plot   
        #plt.plot(vAngDeg, -(JOpt_min - np.log10(np.sum(np.abs(JOpt), 1)))/(JOpt_max - JOpt_min));#DBF plot   
        #plt.ioff();
        #plt.show();
        string_aux = 'DBF_Azimuth_Spectrum_Frame_'+str(Frame_selected)+'_Total'
        name_string = string_aux + '.png'

        #fig50.savefig(name_string, bbox_inches='tight') 
        fig50.clf()

        ###### ELEVATION - Compare MUSIC and DBF #####
        fig60 = plt.figure(60, figsize=(9, 9));
        print("")        
        print("Plot DBF - ELEVATION")        
        print("JOpt_Elv.shape", JOpt_Elv.shape)        # 8 channels x 605 targets
        print("vAngDeg_Elv", vAngDeg_Elv)        # 8 channels x 605 targets
        print("")        
        #JOpt_min = np.min(np.log10(np.sum(np.abs(JOpt), 1))); 
        #JOpt_max = np.max(np.log10(np.sum(np.abs(JOpt), 1)));


        
        print("np.sum(np.abs(output_3d_fft_Elv), 1)",np.sum(np.abs(output_3d_fft_Elv), 1))
        print("np.log10(np.sum(np.abs(output_3d_fft_Elv), 1))",np.log10(np.sum(np.abs(output_3d_fft_Elv), 1)))

        JOpt_min_Elv = np.min(np.log10(np.sum(np.abs(output_3d_fft_Elv), 1))); 
        JOpt_max_Elv = np.max(np.log10(np.sum(np.abs(output_3d_fft_Elv), 1)));

        print("JOpt_min_Elv", JOpt_min_Elv)
        print("JOpt_max_Elv", JOpt_max_Elv)
        print("JOpt_Elv.shape",JOpt_Elv.shape)


        print("vAngDeg_Elv", vAngDeg_Elv)
        print("JOpt_Elv.shape", JOpt_Elv.shape)
        print("output_3d_fft_Elv.shape", output_3d_fft_Elv.shape)

        yaxis_Elv = -(JOpt_min_Elv - np.log10(np.sum(np.abs(output_3d_fft_Elv), 1)))/(JOpt_max_Elv - JOpt_min_Elv)
        #yaxis = -(JOpt_min - np.log10(np.sum(np.abs(JOpt), 1)))/(JOpt_max - JOpt_min)

        print("yaxis_Elv.shape",yaxis_Elv.shape)
        print("yaxis_Elv",yaxis_Elv)

        plt.plot(vAngDeg_Elv, -(JOpt_min_Elv - np.log10(np.sum(np.abs(output_3d_fft_Elv), 1)))/(JOpt_max_Elv - JOpt_min_Elv));#DBF plot   
        #plt.plot(vAngDeg, -(JOpt_min - np.log10(np.sum(np.abs(JOpt), 1)))/(JOpt_max - JOpt_min));#DBF plot   
        #plt.ioff();
        #plt.show();
        string_aux_Elv = 'DBF_Elevation_Spectrum_Frame_'+str(Frame_selected)+'_Total'
        name_string_Elv = string_aux_Elv + '.png'

        #fig60.savefig(name_string_Elv, bbox_inches='tight') 
        fig60.clf()


        #del rd1, rd2, rd3, rd4, rd_total, X_rd_total_np, X_rd_total
        gc.collect()
        #objgraph.show_most_common_types()


        ### End frame loop
path = "microRange_DOppler_signature.csv"
csv_writer(data_csv, path)
plt.close('all')

print("Finished...")
