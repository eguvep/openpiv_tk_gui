#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''Parallel Processing of PIV images.'''

__licence__ = '''
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

__email__= 'vennemann@fh-muenster.de'

import openpiv.tools as piv_tls
import openpiv.preprocess as piv_pre
import openpiv.process as piv_prc
import openpiv.windef as piv_wdf
import openpiv.validation as piv_vld
import openpiv.filters as piv_flt
import openpiv.scaling as piv_scl
import openpiv.smoothn as piv_smt

import time
import numpy as np

from scipy.ndimage.filters import gaussian_filter, gaussian_laplace
from openpivgui.open_piv_gui_tools import create_save_vec_fname
from openpivgui.PreProcessing import gen_background, process_images


class MultiProcessing(piv_tls.Multiprocesser):
    '''Parallel processing, based on the corrresponding OpenPIV class.

    Do not run from the interactive shell or within IDLE! Details at:
    https://docs.python.org/3.6/library/multiprocessing.html#using-a-pool-of-workers

    Parameters
    ----------
    params : OpenPivParams
        A parameter object.
    '''

    def __init__(self, params):
        '''Standard initialization method.

        For separating GUI and PIV code, the output filenames are
        generated here and not in OpenPivGui. In this way, this object
        might also be useful independently from OpenPivGui.
        '''
        self.p = params 
        
        # generate background if needed
        if self.p['background_subtract'] == True and self.p['background_type'] != 'minA - minB':
            self.background = gen_background(self.p)
        else:
            self.background = None
            
        # custom image sequence with (1+[1+x]), (2+[2+x]) and ((1+[1+x]), (3+[3+x]))
        if self.p['sequence'] == '(1+2),(2+3)':
            step = 1
        else: step = 2
        self.files_a = self.p['fnames'][0::step]
        self.files_b = self.p['fnames'][self.p['skip']::step]
        
        # making sure files_a is the same length as files_b
        diff = len(self.files_a)-len(self.files_b) 
        if diff != 0:
            for i in range (diff):
                self.files_a.pop(len(self.files_b))
        print('Number of a files: ' + str(len(self.files_a)))
        print('Number of b files: ' + str(len(self.files_b)))
        
        if self.p['swap_files']:
            self.files_a, self.files_b = self.files_b, self.files_a
        
        self.n_files = len(self.files_a)
        self.save_fnames = []
                                 
        if self.p['evaluation_method'] == 'Direct Correlation': # disassociate the GUI selection from
                                                                # the evaluation to remove white space
            evaluation_method = 'DCC'
        else:
            evaluation_method = 'FFT'
        
        postfix = '_piv_' + evaluation_method + '_'
        for n in range(self.n_files):
            self.save_fnames.append(
                create_save_vec_fname(path=self.files_a[n],
                                      basename=self.p['vec_fname'],
                                      postfix=postfix,
                                      count=n,
                                      max_count=self.n_files))

    def get_save_fnames(self):
        '''Return a list of result filenames.

        Returns:
            str[]: List of filenames with resulting PIV data.
        '''
        return(self.save_fnames)
        
    def process(self, args):
        '''Process chain as configured in the GUI.

        Parameters
        ----------
        args : tuple
            Tuple as expected by the inherited run method:
            file_a (str) -- image file a
            file_b (str) -- image file b
            counter (int) -- index pointing to an element of the filename list
        '''
        file_a, file_b, counter = args
        frame_a = piv_tls.imread(file_a)
        frame_b = piv_tls.imread(file_b)  
        
        #Smoothning script borrowed from openpiv.windef
        s = self.p['smoothn_val']
        def smoothn(u, s): 
            s = s
            u,dummy_u1,dummy_u2,dummy_u3=piv_smt.smoothn(u,s=s, isrobust=self.p['robust'])
            return(u) 
        
        # delimiters placed here for safety
        delimiter = self.p['separator']
        if delimiter == 'tab': delimiter = '\t' 
        if delimiter == 'space': delimiter = ' '
        
        # preprocessing
        print('\nPre-pocessing image pair: {}'.format(counter+1))
        if self.p['background_subtract'] == True and self.p['background_type'] == 'minA - minB':
            self.background = gen_background(self.p, frame_a, frame_b)
            
        frame_a = frame_a.astype(np.int32); frame_a = process_images(self.p, frame_a, 
                                                                     background = self.background)
        frame_b = frame_b.astype(np.int32); frame_b = process_images(self.p, frame_b, 
                                                                     background = self.background)
        print('Evaluating image pair: {}'.format(counter + 1))
        # evaluation
        if self.p['evaluation_method'] == 'Direct Correlation':
            u, v, sig2noise = piv_prc.extended_search_area_piv(
                frame_a.astype(np.int32), frame_b.astype(np.int32),
                window_size      = self.p['corr_window'],
                search_area_size = self.p['search_area'],
                subpixel_method  = self.p['subpixel_method'],
                overlap          = self.p['overlap'],
                dt               = self.p['dt'],
                sig2noise_method = self.p['sig2noise_method'])
            x, y = piv_prc.get_coordinates(
                image_size       = frame_a.shape,
                window_size      = self.p['corr_window'],
                overlap          = self.p['overlap'])
            
            if self.p['smoothn'] == True:
                u = smoothn(u, s)
                v = smoothn(v, s) 
                print('Finished smoothning data for image pair: {}.'.format(counter+1))
            
            x,y,u,v=piv_scl.uniform(x,y,u,v, scaling_factor=self.p['scale'])
            if self.p['smoothn_each_pass'] == True:
                u = smoothn(u)
                v = smoothn(v) 
                print('Finished smoothning results for image pair: {}.'.format(counter+1))
            
            if self.p['flip_u']:
                u = np.flipud(u)

            if self.p['flip_v']:
                   v = np.flipud(v)

            if self.p['invert_u']:
                 u *= -1

            if self.p['invert_v']:
                v *= -1
                
            x,y,u,v=piv_scl.uniform(x,y,u,v, scaling_factor=self.p['scale'])            
            piv_tls.save(x, y, u, v, sig2noise, self.save_fnames[counter])
            print('Processed image pair: {}.'.format(counter+1))
            
        else:
            # evaluation first pass
            overlap_percent = 0.5
            passes = 1
            if self.p['custom_windowing']:
                corr_window_0   = self.p['corr_window_1']
                overlap_0       = self.p['overlap_1']
                overlap_percent = overlap_0 / corr_window_0 
                for i in range(2, 8):
                    if self.p['pass_%1d' % i]:
                        passes += 1
                    else:
                        break;
                        
            else:
                passes = self.p['coarse_factor']
                if self.p['grid_refinement'] == 'all passes' and self.p['coarse_factor'] != 1: 
                    corr_window_0 = self.p['corr_window'] * 2**(self.p['coarse_factor'] - 1)
                    overlap_0     = self.p['overlap'] * 2**(self.p['coarse_factor'] - 1)

                # Refine all passes after first when there are more than 1 pass.    
                elif self.p['grid_refinement'] == '2nd pass on' and self.p['coarse_factor'] != 1: 
                    corr_window_0 = self.p['corr_window'] * 2**(self.p['coarse_factor'] - 2)
                    overlap_0     = self.p['overlap'] * 2**(self.p['coarse_factor'] - 2)

                # If >>none<< is selected or something goes wrong,
                # the window size would remain the same.    
                else:
                    corr_window_0 = self.p['corr_window']
                    overlap_0     = self.p['overlap']

            x, y, u, v, sig2noise = piv_wdf.first_pass(
                frame_a.astype(np.int32), frame_b.astype(np.int32),
                corr_window_0,
                overlap_0,
                passes, # number of passes
                do_sig2noise       = True,
                correlation_method = self.p['corr_method'], # 'circular' or 'linear'
                subpixel_method    = self.p['subpixel_method'])

            # validating first pass
            u, v, mask = piv_vld.local_median_val(
                u, v,
                u_threshold = self.p['fp_local_med'],
                v_threshold = self.p['fp_local_med'],
                size        = self.p['fp_local_med_size'])  

            if self.p['fp_vld_global_threshold']:
                u, v, Mask = piv_vld.global_val(
                    u, v,
                    u_thresholds=(self.p['fp_MinU'],self.p['fp_MaxU']),
                    v_thresholds=(self.p['fp_MinV'],self.p['fp_MaxV']))
                mask += Mask # consolidate effects of mask

            u, v = piv_flt.replace_outliers(
                    u, v,
                    method      = self.p['adv_repl_method'],
                    max_iter    = self.p['adv_repl_iter'],
                    kernel_size = self.p['adv_repl_kernel'])
            print('Filtered first pass result of image pair: {}.'.format(counter+1)) 

            # smoothning  before deformation if 'each pass' is selected
            if self.p['smoothn_each_pass']:
                if self.p['smoothn_first_more']:
                    s *=2
                u = smoothn(u, s); v = smoothn(v, s) 
                print('Smoothned pass 1 for image pair: {}.'.format(counter+1))
                s = self.p['smoothn_val']

            print('Finished pass 1 for image pair: {}.'.format(counter+1))
            print("window size: "   + str(corr_window_0))
            print('overlap: '       + str(overlap_0), '\n')  

            # evaluation of all other passes
            if passes != 1:
                iterations = passes - 1
                for i in range(2, passes + 1):
                    # setting up the windowing of each pass
                    if self.p['custom_windowing']:
                        corr_window = self.p['corr_window_%1d' % i]
                        overlap = int(corr_window * overlap_percent)
                    else:
                        if self.p['grid_refinement'] == 'all passes' or
                        self.p['grid_refinement'] == '2nd pass on':
                            corr_window = self.p['corr_window'] * 2**(iterations - 1)
                            overlap     = self.p['overlap'] * 2**(iterations - 1) 

                        else:
                            corr_window = self.p['corr_window']
                            overlap     = self.p['overlap']

                    x, y, u, v, sig2noise, mask = piv_wdf.multipass_img_deform(
                        frame_a.astype(np.int32), frame_b.astype(np.int32),
                        corr_window,
                        overlap,
                        passes, # number of iterations
                        i, # current iteration
                        x, y, u, v,
                        correlation_method   = self.p['corr_method'],
                        subpixel_method      = self.p['subpixel_method'],
                        do_sig2noise         = True,
                        sig2noise_mask       = self.p['adv_s2n_mask'],
                        MinMaxU              = (self.p['sp_MinU'], self.p['sp_MaxU']),
                        MinMaxV              = (self.p['sp_MinV'], self.p['sp_MaxV']),
                        std_threshold        = self.p['sp_global_std_threshold'],
                        median_threshold     = self.p['sp_local_med_threshold'],
                        median_size          = self.p['sp_local_med_size'],
                        filter_method        = self.p['adv_repl_method'],
                        max_filter_iteration = self.p['adv_repl_iter'],
                        filter_kernel_size   = self.p['adv_repl_kernel'],
                        interpolation_order  = self.p['adv_interpolation_order'])       

                    # smoothning each individual pass if 'each pass' is selected
                    if self.p['smoothn_each_pass']:
                        u = smoothn(u, s); v = smoothn(v, s) 
                        print('Smoothned pass {} for image pair: {}.'.format(i,counter+1))

                    print('Finished pass {} for image pair: {}.'.format(i,counter+1))
                    print("window size: "   + str(corr_window))
                    print('overlap: '       + str(overlap), '\n')
                    iterations -= 1

            if self.p['flip_u']:
                u = np.flipud(u)

            if self.p['flip_v']:
                   v = np.flipud(v)

            if self.p['invert_u']:
                 u *= -1

            if self.p['invert_v']:
                v *= -1

            # scaling
            u = u/self.p['dt']
            v = v/self.p['dt']
            x,y,u,v=piv_scl.uniform(x,y,u,v, scaling_factor=self.p['scale']) 
            
            # save data to file.
            out = np.vstack([m.ravel() for m in [x, y, u, v, mask, sig2noise]])
            np.savetxt(self.save_fnames[counter], out.T, fmt='%8.4f', delimiter=delimiter)
            print('Processed image pair: {}.'.format(counter+1))
