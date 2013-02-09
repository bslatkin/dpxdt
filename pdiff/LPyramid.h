/*
Laplacian Pyramid
Copyright (C) 2006 Yangli Hector Yee

This program is free software; you can redistribute it and/or modify it under the terms of the
GNU General Public License as published by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program;
if not, write to the Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
*/
#ifndef _LPYRAMID_H
#define _LPYRAMID_H

#define MAX_PYR_LEVELS 8

class LPyramid
{
public:	
	LPyramid(float *image, int width, int height);
	virtual ~LPyramid();
	float Get_Value(int x, int y, int level);
protected:
	float *Copy(float *img);
	void Convolve(float *a, float *b);
	
	// Succesively blurred versions of the original image
	float *Levels[MAX_PYR_LEVELS];

	int Width;
	int Height;
};

#endif // _LPYRAMID_H

