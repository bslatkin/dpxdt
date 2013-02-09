// ==========================================================
// FreeImage 3 Test Script
//
// Design and implementation by
// - Hervé Drolon (drolon@infonie.fr)
//
// This file is part of FreeImage 3
//
// COVERED CODE IS PROVIDED UNDER THIS LICENSE ON AN "AS IS" BASIS, WITHOUT WARRANTY
// OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, WITHOUT LIMITATION, WARRANTIES
// THAT THE COVERED CODE IS FREE OF DEFECTS, MERCHANTABLE, FIT FOR A PARTICULAR PURPOSE
// OR NON-INFRINGING. THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE COVERED
// CODE IS WITH YOU. SHOULD ANY COVERED CODE PROVE DEFECTIVE IN ANY RESPECT, YOU (NOT
// THE INITIAL DEVELOPER OR ANY OTHER CONTRIBUTOR) ASSUME THE COST OF ANY NECESSARY
// SERVICING, REPAIR OR CORRECTION. THIS DISCLAIMER OF WARRANTY CONSTITUTES AN ESSENTIAL
// PART OF THIS LICENSE. NO USE OF ANY COVERED CODE IS AUTHORIZED HEREUNDER EXCEPT UNDER
// THIS DISCLAIMER.
//
// Use at your own risk!
// ==========================================================


#include "TestSuite.h"

void  
testBuildMPage(const char *src_filename, const char *dst_filename, FREE_IMAGE_FORMAT dst_fif, unsigned bpp) {
	// get the file type
	FREE_IMAGE_FORMAT src_fif = FreeImage_GetFileType(src_filename);
	// load the file
	FIBITMAP *src = FreeImage_Load(src_fif, src_filename, 0); //24bit image 

	FIMULTIBITMAP *out = FreeImage_OpenMultiBitmap(dst_fif, dst_filename, TRUE, FALSE, FALSE); 
	for(int size = 16; size <= 48; size += 16 ) { 
		FIBITMAP *rescaled = FreeImage_Rescale(src, size, size, FILTER_CATMULLROM);

		if(FreeImage_GetBPP(rescaled) != bpp) {
			// convert to the requested bitdepth
			FIBITMAP *tmp = NULL;
			switch(bpp) {
				case 8:
					tmp = FreeImage_ConvertTo8Bits(rescaled);
					break;
				case 24:
					tmp = FreeImage_ConvertTo24Bits(rescaled);
					break;
			}
			assert(tmp != NULL);
			FreeImage_Unload(rescaled); 
			rescaled = tmp;
		}

		FreeImage_AppendPage(out, rescaled); 
		FreeImage_Unload(rescaled); 
	} 
	
	FreeImage_Unload(src); 
	
	FreeImage_CloseMultiBitmap(out, 0); 

}

void testMPageCache(const char *src_filename, const char *dst_filename) {

	BOOL keep_cache_in_memory = FALSE;

	// get the file type
	FREE_IMAGE_FORMAT src_fif = FreeImage_GetFileType(src_filename);
	// load the file
	FIBITMAP *src = FreeImage_Load(src_fif, src_filename, 0); //24bit image 
	assert(src != NULL);

	// convert to 24-bit
	if(FreeImage_GetBPP(src) != 24) {
		FIBITMAP *tmp = FreeImage_ConvertTo24Bits(src);
		assert(tmp != NULL);
		FreeImage_Unload(src); 
		src = tmp;
	}

	FIMULTIBITMAP *out = FreeImage_OpenMultiBitmap(FIF_TIFF, dst_filename, TRUE, FALSE, keep_cache_in_memory); 

	// attempt to create 16 480X360 images in a 24-bit TIFF multipage file
	FIBITMAP *rescaled = FreeImage_Rescale(src, 480, 360, FILTER_CATMULLROM);
	for(int i = 0; i < 16; i++) { 		
		FreeImage_AppendPage(out, rescaled); 
	} 
	FreeImage_Unload(rescaled); 
	
	FreeImage_Unload(src); 
	
	FreeImage_CloseMultiBitmap(out, 0); 
}

// --------------------------------------------------------------------------

BOOL testCloneMultiPage(FREE_IMAGE_FORMAT fif, const char *input, const char *output, int output_flag) {

	BOOL bMemoryCache = TRUE;

	// Open src file (read-only, use memory cache)
	FIMULTIBITMAP *src = FreeImage_OpenMultiBitmap(fif, input, FALSE, TRUE, bMemoryCache);

	if(src) {
		// Open dst file (creation, use memory cache)
		FIMULTIBITMAP *dst = FreeImage_OpenMultiBitmap(fif, output, TRUE, FALSE, bMemoryCache);

		// Get src page count
		int count = FreeImage_GetPageCount(src);

		// Clone src to dst
		for(int page = 0; page < count; page++) {
			// Load the bitmap at position 'page'
			FIBITMAP *dib = FreeImage_LockPage(src, page);
			if(dib) {
				// add a new bitmap to dst
				FreeImage_AppendPage(dst, dib);
				// Unload the bitmap (do not apply any change to src)
				FreeImage_UnlockPage(src, dib, FALSE);
			}
		}

		// Close src
		FreeImage_CloseMultiBitmap(src, 0);
		// Save and close dst
		FreeImage_CloseMultiBitmap(dst, output_flag);

		return TRUE;
	}

	return FALSE;
}

// --------------------------------------------------------------------------

void testLockDeleteMultiPage(const char *input) {

	BOOL bCreateNew = FALSE;
	BOOL bReadOnly = FALSE;
	BOOL bMemoryCache = TRUE;

	// Open src file (read/write, use memory cache)
	FREE_IMAGE_FORMAT fif = FreeImage_GetFileType(input);
	FIMULTIBITMAP *src = FreeImage_OpenMultiBitmap(fif, input, bCreateNew, bReadOnly, bMemoryCache);
	
	if(src) {
		// get the page count
		int count = FreeImage_GetPageCount(src);
		if(count > 2) {
			// Load the bitmap at position '2'
			FIBITMAP *dib = FreeImage_LockPage(src, 2);
			if(dib) {
				FreeImage_Invert(dib);
				// Unload the bitmap (apply change to src)
				FreeImage_UnlockPage(src, dib, TRUE);
			}
		}
		// Close src
		FreeImage_CloseMultiBitmap(src, 0);
	}

	src = FreeImage_OpenMultiBitmap(fif, input, bCreateNew, bReadOnly, bMemoryCache);
	
	if(src) {
		// get the page count
		int count = FreeImage_GetPageCount(src);
		if(count > 1) {
			// delete page 0
			FreeImage_DeletePage(src, 0);
		}
		// Close src
		FreeImage_CloseMultiBitmap(src, 0);
	}
}

// --------------------------------------------------------------------------

void testMultiPage(const char *lpszPathName) {
	printf("testMultiPage ...\n");

	// test multipage creation
	testBuildMPage(lpszPathName, "sample.ico", FIF_ICO, 24);
	testBuildMPage(lpszPathName, "sample.tif", FIF_TIFF, 24);
	testBuildMPage(lpszPathName, "sample.gif", FIF_GIF, 8);

	// test multipage copy
	testCloneMultiPage(FIF_TIFF, "sample.tif", "clone.tif", TIFF_LZW);

	// test multipage lock & delete
	testLockDeleteMultiPage("clone.tif");

	// test multipage cache
	testMPageCache(lpszPathName, "mpages.tif");
}
