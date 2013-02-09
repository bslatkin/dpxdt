/*
RGBAImage.cpp
Copyright (C) 2006 Yangli Hector Yee

(This entire file was rewritten by Jim Tilander)

This program is free software; you can redistribute it and/or modify it under the terms of the
GNU General Public License as published by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program;
if not, write to the Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
*/

#include "RGBAImage.h"
#include "FreeImage.h"
#include <cstdio>
#include <cstring>

RGBAImage* RGBAImage::DownSample() const {
   if (Width <=1 || Height <=1) return NULL;
   int nw = Width / 2;
   int nh = Height / 2;
   RGBAImage* img = new RGBAImage(nw, nh, Name.c_str());
   for (int y = 0; y < nh; y++) {
      for (int x = 0; x < nw; x++) {
         int d[4];
         // Sample a 2x2 patch from the parent image.
         d[0] = Get(2 * x + 0, 2 * y + 0);
         d[1] = Get(2 * x + 1, 2 * y + 0);
         d[2] = Get(2 * x + 0, 2 * y + 1);
         d[3] = Get(2 * x + 1, 2 * y + 1);
         int rgba = 0;
         // Find the average color.
         for (int i = 0; i < 4; i++) {
            int c = (d[0] >> (8 * i)) & 0xFF;
            c += (d[1] >> (8 * i)) & 0xFF;
            c += (d[2] >> (8 * i)) & 0xFF;
            c += (d[3] >> (8 * i)) & 0xFF;
            c /= 4;
            rgba |= (c & 0xFF) << (8 * i);
         }
         img->Set(x, y, rgba);
      }
   }
   return img;
}

bool RGBAImage::WriteToFile(const char* filename)
{
	const FREE_IMAGE_FORMAT fileType = FreeImage_GetFIFFromFilename(filename);
	if(FIF_UNKNOWN == fileType)
	{
		printf("Can't save to unknown filetype %s\n", filename);
		return false;
	}

	FIBITMAP* bitmap = FreeImage_Allocate(Width, Height, 32, 0x000000ff, 0x0000ff00, 0x00ff0000);
	if(!bitmap)
	{
		printf("Failed to create freeimage for %s\n", filename);
		return false;
	}

	const unsigned int* source = Data;
	for( int y=0; y < Height; y++, source += Width )
	{
		unsigned int* scanline = (unsigned int*)FreeImage_GetScanLine(bitmap, Height - y - 1 );
		memcpy(scanline, source, sizeof(source[0]) * Width);
	}	
	
	FreeImage_SetTransparent(bitmap, false);
	FIBITMAP* converted = FreeImage_ConvertTo24Bits(bitmap);
	
	
	const bool result = !!FreeImage_Save(fileType, converted, filename);
	if(!result)
		printf("Failed to save to %s\n", filename);
	
	FreeImage_Unload(converted);
	FreeImage_Unload(bitmap);
	return result;
}

RGBAImage* RGBAImage::ReadFromFile(const char* filename)
{
	const FREE_IMAGE_FORMAT fileType = FreeImage_GetFileType(filename);
	if(FIF_UNKNOWN == fileType)
	{
		printf("Unknown filetype %s\n", filename);
		return 0;
	}
	
	FIBITMAP* freeImage = 0;
	if(FIBITMAP* temporary = FreeImage_Load(fileType, filename, 0))
	{
		freeImage = FreeImage_ConvertTo32Bits(temporary);
		FreeImage_Unload(temporary);
	}
	if(!freeImage)
	{
		printf( "Failed to load the image %s\n", filename);
		return 0;
	}

	const int w = FreeImage_GetWidth(freeImage);
	const int h = FreeImage_GetHeight(freeImage);

	RGBAImage* result = new RGBAImage(w, h, filename);
	// Copy the image over to our internal format, FreeImage has the scanlines bottom to top though.
	unsigned int* dest = result->Data;
	for( int y=0; y < h; y++, dest += w )
	{
		const unsigned int* scanline = (const unsigned int*)FreeImage_GetScanLine(freeImage, h - y - 1 );
		memcpy(dest, scanline, sizeof(dest[0]) * w);
	}	

	FreeImage_Unload(freeImage);
	return result;
}


