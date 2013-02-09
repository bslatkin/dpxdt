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

// Local test functions
// ----------------------------------------------------------

void testSupportsNoPixels() {
	for (int i = 0; i < FreeImage_GetFIFCount(); i++) {
		FREE_IMAGE_FORMAT fmt = (FREE_IMAGE_FORMAT)i;
		if (!FreeImage_FIFSupportsNoPixels(fmt)) {
			// 'header only' loading mode is not supported
			continue;
		}
		printf("testSupportsNoPixels (%s) ...\n", FreeImage_GetFormatFromFIF(fmt));
	}
}

/**
Test header only bitmap allocation
*/
BOOL testHeader(const char *lpszPathName) {
	int flags = FIF_LOAD_NOPIXELS;

	FIBITMAP *dib1 = NULL, *dib2 = NULL;

	try {
		FREE_IMAGE_FORMAT fif = FreeImage_GetFIFFromFilename(lpszPathName);

		dib1 = FreeImage_Load(fif, lpszPathName, flags); 
		if(!dib1) throw(1);
		
		dib2 = FreeImage_Clone(dib1); 
		if(!dib2) throw(1);
		
		FreeImage_Unload(dib1); 
		FreeImage_Unload(dib2); 

		return TRUE;
	} 
	catch(int) {
		if(dib1) FreeImage_Unload(dib1); 
		if(dib2) FreeImage_Unload(dib2); 
	}
	
	return FALSE; 
}

/**
Parse metadata attached to a dib
*/
static void ParseMetadata(FIBITMAP *dib, FREE_IMAGE_MDMODEL model) {
	FITAG *tag = NULL;
	FIMETADATA *mdhandle = NULL;

	mdhandle = FreeImage_FindFirstMetadata(model, dib, &tag);

	if(mdhandle) {
		do {
			// get the tag key
			const char *key = FreeImage_GetTagKey(tag);
			// convert the tag value to a string
			const char *value = FreeImage_TagToString(model, tag);

			// print the tag 
			// note that most tags do not have a description, 
			// especially when the metadata specifications are not available
			if(FreeImage_GetTagDescription(tag)) {
				//cout << FreeImage_GetTagKey(tag) << "=" << value << " - " << FreeImage_GetTagDescription(tag) << "\n";
			} else {
				//cout << FreeImage_GetTagKey(tag) << "=" << value << " - " << "\n";
			}

		} while(FreeImage_FindNextMetadata(mdhandle, &tag));
	}

	FreeImage_FindCloseMetadata(mdhandle);
}

/**
Load the header of a bitmap (without pixel data)
*/
BOOL testHeaderData(const char *lpszPathName) {
	int flags = FIF_LOAD_NOPIXELS;

	FIBITMAP *dib = NULL;

	try {
		// load a file using the FIF_LOAD_NOPIXELS flag
		FREE_IMAGE_FORMAT fif = FreeImage_GetFIFFromFilename(lpszPathName);
		assert(FreeImage_FIFSupportsNoPixels(fif) == TRUE);

		dib = FreeImage_Load(fif, lpszPathName, flags); 
		if(!dib) throw(1);

		// check that dib does not contains pixels
		BOOL bHasPixel = FreeImage_HasPixels(dib);
		assert(bHasPixel == FALSE);

		// use accessors
		FREE_IMAGE_TYPE type = FreeImage_GetImageType(dib);
		unsigned width = FreeImage_GetWidth(dib);
		unsigned height = FreeImage_GetHeight(dib);
		unsigned bpp = FreeImage_GetBPP(dib);
		// parse some metadata (see e.g. FreeImage_FindFirstMetadata)
		ParseMetadata(dib, FIMD_COMMENTS);
		ParseMetadata(dib, FIMD_EXIF_MAIN);
		ParseMetadata(dib, FIMD_EXIF_EXIF);
		ParseMetadata(dib, FIMD_EXIF_GPS);
		ParseMetadata(dib, FIMD_EXIF_MAKERNOTE);
		ParseMetadata(dib, FIMD_IPTC);
		ParseMetadata(dib, FIMD_XMP);

		// you cannot access pixels
		BYTE *bits = FreeImage_GetBits(dib);
		assert(bits == NULL);
		
		FreeImage_Unload(dib); 

		return TRUE;
	} 
	catch(int) {
		if(dib) FreeImage_Unload(dib); 
	}
	
	return FALSE; 
}

/**
Test loading and saving of Exif raw data
*/
static BOOL 
testExifRawFile(const char *lpszPathName, int load_flags, int save_flags) {
	const char *lpszDstPathName = "raw_exif.jpg";

	FIBITMAP *dib = NULL, *dst = NULL;

	try {
		// load an Exif file (jpeg file)
		FREE_IMAGE_FORMAT fif = FreeImage_GetFIFFromFilename(lpszPathName);

		dib = FreeImage_Load(fif, lpszPathName, load_flags); 
		if(!dib) throw(1);

		// check access to raw Exif data
		FITAG *tag = NULL;
		BOOL bResult = FreeImage_GetMetadata(FIMD_EXIF_RAW, dib, "ExifRaw", &tag);
		if(tag) {
			const char *key = FreeImage_GetTagKey(tag);
			WORD id = FreeImage_GetTagID(tag);
			FREE_IMAGE_MDTYPE type = FreeImage_GetTagType(tag);
			DWORD count = FreeImage_GetTagCount(tag);
			DWORD length = FreeImage_GetTagLength(tag);
			BYTE *value = (BYTE*)FreeImage_GetTagValue(tag);

			// save as jpeg : Exif data should be preserved
			FreeImage_Save(fif, dib, lpszDstPathName, save_flags); 

			// load and check Exif raw data
			fif = FreeImage_GetFileType(lpszDstPathName);

			dst = FreeImage_Load(fif, lpszDstPathName, load_flags); 
			if(!dst) throw(1);

			FITAG *dst_tag = NULL;
			BOOL bResult = FreeImage_GetMetadata(FIMD_EXIF_RAW, dib, "ExifRaw", &dst_tag);
			if(dst_tag) {
				const char *key = FreeImage_GetTagKey(dst_tag);
				WORD dst_id = FreeImage_GetTagID(dst_tag);
				FREE_IMAGE_MDTYPE dst_type = FreeImage_GetTagType(dst_tag);
				DWORD dst_count = FreeImage_GetTagCount(dst_tag);
				DWORD dst_length = FreeImage_GetTagLength(dst_tag);
				BYTE *dst_value = (BYTE*)FreeImage_GetTagValue(dst_tag);

				assert(length == dst_length);
			}
			
			FreeImage_Unload(dst); 
		}

		FreeImage_Unload(dib); 

		return TRUE;
	} 
	catch(int) {
		if(dib) FreeImage_Unload(dib); 
	}
	
	return FALSE; 
}

// Main test functions
// ----------------------------------------------------------

void testHeaderOnly() {
	const char *src_file_jpg = "exif.jpg";
	const char *src_file_png = "sample.png";

	BOOL bResult = TRUE;

	printf("testHeaderOnly ...\n");

	testSupportsNoPixels();
	
	// JPEG plugin
	bResult = testHeader(src_file_jpg);
	assert(bResult);

	bResult = testHeaderData(src_file_jpg);
	assert(bResult);

	// PNG plugin
	bResult = testHeader(src_file_png);
	assert(bResult);

	bResult = testHeaderData(src_file_png);
	assert(bResult);

	// you cannot save 'header only' FIBITMAP
	bResult = testExifRawFile(src_file_jpg, FIF_LOAD_NOPIXELS, 0);
	assert(bResult == FALSE);
}

void testExifRaw() {
	const char *src_file_jpg = "exif.jpg";

	BOOL bResult = TRUE;

	printf("testExifRaw ...\n");

	// Exif raw metadata loading & saving

	// check Exif raw metadata loading & saving
	bResult = testExifRawFile(src_file_jpg, 0, 0);
	assert(bResult);

}
