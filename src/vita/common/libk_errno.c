/*
 * The reference modules used PDCLib's public-domain errno table and helper.
 * _PDCLIB_errno itself is defined among each module's recovered globals so
 * that its original absolute BSS position is retained.
 */

#define _PDCLIB_INT_H _PDCLIB_INT_H
#include <_PDCLIB_int.h>

int *_PDCLIB_errno_func(void) {
	return &_PDCLIB_errno;
}

char const *_PDCLIB_errno_texts[] = {
	"",
	"ERANGE (Range error)",
	"EDOM (Domain error)",
	"EIO (I/O error)",
	"EUNKNOWN (Unknown error)",
	"EINVAL (Invalid parameter value)",
	"ERETRY (I/O retries exceeded)",
};
