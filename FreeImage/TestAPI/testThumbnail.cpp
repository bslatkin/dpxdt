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

/**
Test thumbnail loading
*/
static BOOL testLoadThumbnail(const char *lpszPathName, int flags) {
	FIBITMAP *dib = NULL;

	try {
		FREE_IMAGE_FORMAT fif = FreeImage_GetFileType(lpszPathName);

		dib = FreeImage_Load(fif, lpszPathName, flags); 
		if(!dib) throw(1);

		FIBITMAP *thumbnail = FreeImage_GetThumbnail(dib);
		if(!thumbnail) throw(1);

		unsigned t_width = FreeImage_GetWidth(thumbnail);
		unsigned t_height = FreeImage_GetHeight(thumbnail);
		printf("... %s contains a thumbnail whose size is %dx%d\n", lpszPathName, t_width, t_height);
		
		FreeImage_Unload(dib); 

		return TRUE;
	} 
	catch(int) {
		if(dib) FreeImage_Unload(dib); 
	}
	
	return FALSE; 
}

/**
Test thumbnail saving
*/
static BOOL testSaveThumbnail(const char *lpszPathName, int flags) {
	BOOL bResult = FALSE;
	FIBITMAP *dib = NULL;
	FIBITMAP *t_clone = NULL;
	const char *lpszImagePathName = "exif_new_thumb.jpg";

	try {
		FREE_IMAGE_FORMAT fif = FreeImage_GetFileType(lpszPathName);

		// load the dib
		dib = FreeImage_Load(fif, lpszPathName, flags); 
		if(!dib) throw(1);

		// get a link to the attached thumbnail
		FIBITMAP *thumbnail = FreeImage_GetThumbnail(dib);
		if(!thumbnail) throw(1);

		// clone the thumbnail and modify it (e.g. convert to greyscale)
		assert(FreeImage_GetBPP(thumbnail) == 24);
		t_clone = FreeImage_ConvertTo8Bits(thumbnail);
		if(!t_clone) throw(1);

		// replace the thumbnail
		FreeImage_SetThumbnail(dib, t_clone);
		// no longer needed
		FreeImage_Unload(t_clone);
		t_clone = NULL;

		// save as a new image
		// be sure to delete the Exif segment as it can also contain a thumbnail
		// this thumbnail will then be loaded instead of the one we store in the JFXX segment
		fif = FIF_TIFF;
		FreeImage_SetMetadata(FIMD_EXIF_RAW, dib, NULL, NULL);
		bResult = FreeImage_Save(fif, dib, lpszImagePathName, 0);
		assert(bResult);

		// no longer needed		
		FreeImage_Unload(dib);

		// reload the image and check its thumbnail
		dib = FreeImage_Load(fif, lpszImagePathName, 0); 
		if(!dib) throw(1);

		// get a link to the attached thumbnail
		FIBITMAP *new_thumbnail = FreeImage_GetThumbnail(dib);
		if(!new_thumbnail) throw(1);

		// check that the thumbnail is greyscale
		// note that with JPEG, we cannot compare pixels between new_thumbnail and t_clone
		// because JPEG compression will modify the pixels
		assert(FreeImage_GetBPP(new_thumbnail) == 8);

		FreeImage_Unload(dib);

		return TRUE;
	} 
	catch(int) {
		if(dib) FreeImage_Unload(dib); 
		if(t_clone) FreeImage_Unload(t_clone); 
	}
	
	return FALSE; 
}

/**
Thest thumbnail functions
*/
void testThumbnail(const char *lpszPathName, int flags) {
	BOOL bResult = FALSE;

	printf("testThumbnail ...\n");

	// Thumbnail loading
	bResult = testLoadThumbnail(lpszPathName, flags);
	assert(bResult);

	// Thumbnail saving
	bResult = testSaveThumbnail(lpszPathName, flags);
	assert(bResult);

}

