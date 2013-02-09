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

// --------------------------------------------------------------------------

static BOOL 
extractPagesFromMemory(FREE_IMAGE_FORMAT fif, FIMEMORY *stream) {
	char filename[256];
	// open the multipage bitmap stream as read-only
	FIMULTIBITMAP *src = FreeImage_LoadMultiBitmapFromMemory(fif, stream, 0);
	if(src) {
		// get the page count
		int count = FreeImage_GetPageCount(src);
		// extract all pages
		for(int page = 0; page < count; page++) {
			// load the bitmap at position 'page'
			FIBITMAP *dib = FreeImage_LockPage(src, page);
			if(dib) {
				// save the page
				sprintf(filename, "page%d.%s", page, FreeImage_GetFormatFromFIF(fif));
				FreeImage_Save(fif, dib, filename, 0);
				// Unload the bitmap (do not apply any change to src)
				FreeImage_UnlockPage(src, dib, FALSE);
			} else {
				// an error occured: free the multipage bitmap handle and return
				FreeImage_CloseMultiBitmap(src, 0);
				return FALSE;
			}
		}
	}
	// make sure to close the multipage bitmap handle on exit
	return FreeImage_CloseMultiBitmap(src, 0);
}

void testLoadMultiBitmapFromMemory(const char *lpszPathName) {
	struct stat buf;
	int result;

	// get data associated with lpszPathName
	result = stat(lpszPathName, &buf);
	if(result == 0) {
		// allocate a memory buffer and load temporary data
		BYTE *mem_buffer = (BYTE*)malloc(buf.st_size * sizeof(BYTE));
		if(mem_buffer) {
			FILE *stream = fopen(lpszPathName, "rb");
			if(stream) {
				fread(mem_buffer, sizeof(BYTE), buf.st_size, stream);
				fclose(stream);

				// attach the binary data to a memory stream
				FIMEMORY *hmem = FreeImage_OpenMemory(mem_buffer, buf.st_size);

				// get the file type
				FREE_IMAGE_FORMAT fif = FreeImage_GetFileTypeFromMemory(hmem, 0);

				// extract pages 
				BOOL bSuccess = extractPagesFromMemory(fif, hmem);
				assert(bSuccess);
		
				// close the stream
				FreeImage_CloseMemory(hmem);

			}
		}
		// user is responsible for freeing the data
		free(mem_buffer);
	}
}

// --------------------------------------------------------------------------

BOOL testSaveMultiBitmapToMemory(const char *input, const char *output, int output_flag) {
	BOOL bSuccess;

	BOOL bCreateNew = FALSE;
	BOOL bReadOnly = TRUE;
	BOOL bMemoryCache = TRUE;

	// Open src file (read-only, use memory cache)
	FREE_IMAGE_FORMAT fif = FreeImage_GetFileType(input);
	FIMULTIBITMAP *src = FreeImage_OpenMultiBitmap(fif, input, bCreateNew, bReadOnly, bMemoryCache);

	if(src) {
		// open and allocate a memory stream
		FIMEMORY *dst_memory = FreeImage_OpenMemory();
		
		// save the file to memory
		bSuccess = FreeImage_SaveMultiBitmapToMemory(fif, src, dst_memory, output_flag);
		assert(bSuccess);

		// src is no longer needed: close and free src file
		FreeImage_CloseMultiBitmap(src, 0);

		// get the buffer from the memory stream
		BYTE *mem_buffer = NULL;
		DWORD size_in_bytes = 0;

		bSuccess = FreeImage_AcquireMemory(dst_memory, &mem_buffer, &size_in_bytes);
		assert(bSuccess);

		// save the buffer in a file stream
		FILE *stream = fopen(output, "wb");
		if(stream) {
			fwrite(mem_buffer, sizeof(BYTE), size_in_bytes, stream);
			fclose(stream);
		}
		
		// close and free the memory stream
		FreeImage_CloseMemory(dst_memory);
		
		return TRUE;
	}

	return FALSE;
}

// --------------------------------------------------------------------------

static BOOL  
loadBuffer(const char *lpszPathName, BYTE **buffer, DWORD *length) {
	struct stat file_info;
	int result;

	// get data associated with lpszPathName
	result = stat(lpszPathName, &file_info);
	if(result == 0) {
		// allocate a memory buffer and load temporary data
		*buffer = (BYTE*)malloc(file_info.st_size * sizeof(BYTE));
		if(*buffer) {
			FILE *stream = fopen(lpszPathName, "rb");
			if(stream) {
				*length = (DWORD)fread(*buffer, sizeof(BYTE), file_info.st_size, stream);
				fclose(stream);
				
				return TRUE;
			}
		}
	}

	return FALSE;
}

BOOL testMemoryStreamMultiPageOpenSave(const char *lpszPathName, char *output, int input_flag, int output_flag) {
	BOOL bSuccess = FALSE;

	BYTE *buffer = NULL;
	DWORD buffer_size = 0;

	// load source stream as a buffer, i.e. 
	// allocate a memory buffer and load temporary data
	bSuccess = loadBuffer(lpszPathName, &buffer, &buffer_size);
	assert(bSuccess);

	// attach the binary data to a memory stream
	FIMEMORY *src_stream = FreeImage_OpenMemory(buffer, buffer_size);
	assert(src_stream);

	// open the multipage bitmap stream
	FREE_IMAGE_FORMAT fif = FreeImage_GetFileTypeFromMemory(src_stream, 0);
	FIMULTIBITMAP *src = FreeImage_LoadMultiBitmapFromMemory(fif, src_stream, input_flag);

	// apply some modifications (everything being stored to the cache) ...

	if(src) {
		// get the page count
		int count = FreeImage_GetPageCount(src);
		assert(count > 2);

		// Load the bitmap at position '2'
		FIBITMAP *dib = FreeImage_LockPage(src, 2);
		if(dib) {
			FreeImage_Invert(dib);
			// Unload the bitmap (apply change to src, modifications are stored to the cache)
			FreeImage_UnlockPage(src, dib, TRUE);
		}

		// delete page 0 (modifications are stored to the cache)
		FreeImage_DeletePage(src, 0);

		// insert a new page at position '0' (modifications are stored to the cache)
		FIBITMAP *page = createZonePlateImage(512, 512, 128);
		FreeImage_InsertPage(src, 0, page);
		FreeImage_Unload(page);
	}

	// save the modification into the output stream ...

	if(src) {
		// open and allocate a memory stream
		FIMEMORY *dst_stream = FreeImage_OpenMemory();
		assert(dst_stream);
		
		// save the file to memory
		FreeImage_SaveMultiBitmapToMemory(fif, src, dst_stream, output_flag);

		// src is no longer needed
		// close and free the memory stream
		FreeImage_CloseMemory(src_stream);
		// close and free src file (nothing is done, the cache is cleared)
		FreeImage_CloseMultiBitmap(src, 0);

		// at this point, the input buffer is no longer needed
		// !!! user is responsible for freeing the initial source buffer !!!
		free(buffer); buffer = NULL;
		
		// get the dst buffer from the memory stream
		BYTE *dst_buffer = NULL;
		DWORD size_in_bytes = 0;
		
		FreeImage_AcquireMemory(dst_stream, &dst_buffer, &size_in_bytes);
		
		// save the buffer in a file stream
		FILE *stream = fopen(output, "wb");
		if(stream) {
			fwrite(dst_buffer, sizeof(BYTE), size_in_bytes, stream);
			fclose(stream);
		}
		
		// close and free the memory stream
		FreeImage_CloseMemory(dst_stream);

		return TRUE;
	}

	if(buffer) {
		free(buffer);
	}

	return FALSE;
}

// --------------------------------------------------------------------------

void testMultiPageMemory(const char *lpszPathName) {
	BOOL bSuccess;

	printf("testMultiPageMemory ...\n");
	
	// test FreeImage_LoadMultiBitmapFromMemory
	testLoadMultiBitmapFromMemory(lpszPathName);

	// test FreeImage_SaveMultiBitmapToMemory
	bSuccess = testSaveMultiBitmapToMemory("sample.tif", "mpage-mstream.tif", 0);
	assert(bSuccess);

	// test FreeImage_LoadMultiBitmapFromMemory & FreeImage_SaveMultiBitmapToMemory
	bSuccess = testMemoryStreamMultiPageOpenSave("sample.tif", "mpage-mstream-redirect.tif", 0, 0);
	assert(bSuccess);

}
