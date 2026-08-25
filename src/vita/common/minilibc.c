#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>

void *memset(void *destination, int value, size_t size) {
	unsigned char *output = destination; /* Byte-oriented destination cursor. */
	while (size-- != 0)
		*output++ = (unsigned char)value;
	return destination;
}

void *memcpy(void *destination, const void *source, size_t size) {
	unsigned char       *output = destination;
	const unsigned char *input  = source;
	while (size-- != 0)
		*output++ = *input++;
	return destination;
}

size_t strlen(const char *text) {
	const char *end = text;
	while (*end != '\0')
		++end;
	return (size_t)(end - text);
}

char *strcpy(char *destination, const char *source) {
	char *result = destination;
	do {
		*destination++ = *source;
	} while (*source++ != '\0');
	return result;
}

char *strncpy(char *destination, const char *source, size_t size) {
	char *result = destination;
	while (size != 0 && *source != '\0') {
		*destination++ = *source++;
		--size;
	}
	while (size-- != 0)
		*destination++ = '\0';
	return result;
}

int strcmp(const char *left, const char *right) {
	const unsigned char *a = (const unsigned char *)left;
	const unsigned char *b = (const unsigned char *)right;
	while (*a != '\0' && *a == *b) {
		++a;
		++b;
	}
	return (int)*a - (int)*b;
}

int strncmp(const char *left, const char *right, size_t size) {
	const unsigned char *a = (const unsigned char *)left;
	const unsigned char *b = (const unsigned char *)right;
	while (size != 0) {
		if (*a == '\0' || *a != *b)
			return (int)*a - (int)*b;
		++a;
		++b;
		--size;
	}
	return 0;
}

char *strchr(const char *text, int character) {
	char target = (char)character;
	do {
		if (*text == target)
			return (char *)text;
	} while (*text++ != '\0');
	return NULL;
}

char *strrchr(const char *text, int character) {
	char target = (char)character;
	const char *found = NULL;
	do {
		if (*text == target)
			found = text;
	} while (*text++ != '\0');
	return (char *)found;
}

static int is_delimiter(char character, const char *delimiters) {
	while (*delimiters != '\0') {
		if (character == *delimiters++)
			return 1;
	}
	return 0;
}

char *strtok_r(char *text, const char *delimiters, char **state) {
	char *cursor = text; /* A NULL input resumes from the caller-owned state. */
	if (cursor == NULL) {
		cursor = *state;
		if (cursor == NULL)
			return NULL;
	}
	while (*cursor != '\0' && is_delimiter(*cursor, delimiters))
		++cursor;
	if (*cursor == '\0') {
		*state = NULL;
		return NULL;
	}

	char *token = cursor;
	while (*cursor != '\0' && !is_delimiter(*cursor, delimiters))
		++cursor;
	if (*cursor != '\0') {
		*cursor++ = '\0';
		*state = cursor;
	} else {
		*state = NULL;
	}
	return token;
}

typedef struct FormatOutput {
	char  *buffer;   /* Caller-provided destination. */
	size_t capacity; /* Total destination size, including the terminator. */
	size_t length;   /* Characters that formatting attempted to emit. */
} FormatOutput;

static void emit_character(FormatOutput *output, char character) {
	if (output->capacity != 0 && output->length + 1 < output->capacity)
		output->buffer[output->length] = character; /* Reserve one byte for NUL. */
	++output->length;
}

static void emit_string(FormatOutput *output, const char *text) {
	while (*text != '\0')
		emit_character(output, *text++);
}

static void emit_decimal(
	FormatOutput *output,
	int value,
	unsigned int width,
	char padding
) {
	char         digits[11];
	unsigned int count = 0;
	uint32_t     magnitude;
	if (value < 0) {
		emit_character(output, '-');
		if (width != 0)
			--width;
		magnitude = 0u - (uint32_t)value;
	} else {
		magnitude = (uint32_t)value;
	}
	do {
		digits[count++] = (char)('0' + magnitude % 10u);
		magnitude /= 10u;
	} while (magnitude != 0);
	while (count < width) {
		emit_character(output, padding);
		--width;
	}
	while (count != 0)
		emit_character(output, digits[--count]);
}

static int format(
	char *buffer,
	size_t capacity,
	const char *format_string,
	va_list arguments
) {
	FormatOutput output = { buffer, capacity, 0 }; /* Length follows snprintf semantics. */
	while (*format_string != '\0') {
		if (*format_string++ != '%') {
			emit_character(&output, format_string[-1]);
			continue;
		}
		if (*format_string == '%') {
			emit_character(&output, *format_string++);
			continue;
		}

		char padding = ' '; /* Only space and zero padding are supported. */
		if (*format_string == '0') {
			padding = '0';
			++format_string;
		}
		unsigned int width = 0; /* Decimal field width parsed from the format. */
		while (*format_string >= '0' && *format_string <= '9') {
			width = width * 10u + (unsigned int)(*format_string - '0');
			++format_string;
		}
		if (*format_string == 's') {
			emit_string(&output, va_arg(arguments, const char *));
			++format_string;
		} else if (*format_string == 'd') {
			emit_decimal(&output, va_arg(arguments, int), width, padding);
			++format_string;
		} else if (*format_string != '\0') {
			emit_character(&output, '%');
			emit_character(&output, *format_string++);
		}
	}
	if (capacity != 0) {
		size_t terminator = output.length < capacity
			? output.length
			: capacity - 1;
		buffer[terminator] = '\0'; /* Always terminate a non-empty destination. */
	}
	return (int)output.length;
}

int vsnprintf(
	char *buffer,
	size_t capacity,
	const char *format_string,
	va_list arguments
) {
	return format(buffer, capacity, format_string, arguments);
}

int snprintf(char *buffer, size_t capacity, const char *format_string, ...) {
	va_list arguments;
	va_start(arguments, format_string);
	int result = format(buffer, capacity, format_string, arguments);
	va_end(arguments);
	return result;
}

int sprintf(char *buffer, const char *format_string, ...) {
	va_list arguments;
	va_start(arguments, format_string);
	int result = format(buffer, SIZE_MAX, format_string, arguments);
	va_end(arguments);
	return result;
}
