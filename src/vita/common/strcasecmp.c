/*
 * AdrBubbleBooter's newlib C-locale table marks exactly ASCII A-Z for the
 * 0x20 case fold used by its private strcasecmp implementation.
 */
int strcasecmp(const char *left, const char *right) {
	const unsigned char *a = (const unsigned char *)left;
	const unsigned char *b = (const unsigned char *)right;
	for (;;) {
		unsigned int folded_a = *a; /* Promote before applying the ASCII fold. */
		unsigned int folded_b = *b; /* Promote before applying the ASCII fold. */
		if (folded_a >= 'A' && folded_a <= 'Z')
			folded_a += 'a' - 'A';
		if (folded_b >= 'A' && folded_b <= 'Z')
			folded_b += 'a' - 'A';
		int difference = (int)folded_a - (int)folded_b; /* Match libc comparison signs. */
		if (difference != 0 || *b == '\0')
			return difference;
		++a;
		++b;
	}
}
