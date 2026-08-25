/*
	Adrenaline
	Copyright (C) 2016-2019, TheFloW, LMAN <LeecherMan>

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
*/

#include <pspkernel.h>
#include <systemctrl.h>
#include <string.h>

#define MAX_THREADS 32

SceUID threads[MAX_THREADS];
int thread_count = 0;
int suspended_count = 0;

void SuspendThreads() {	
	sceKernelGetThreadmanIdList(SCE_KERNEL_TMID_Thread, threads, sizeof(threads) / sizeof(SceUID), &thread_count);
	int i;
	for (i = 0; i < thread_count; i++) {
		SceKernelThreadInfo info;
		info.size = sizeof(SceKernelThreadInfo);
		if (sceKernelReferThreadStatus(threads[i], &info) == 0) {
			if ((info.status & PSP_THREAD_RUNNING) == 0 && (info.status & PSP_THREAD_SUSPEND) == 0) {
					continue;
			}
		}
		threads[i] = -1;
	}
	for (i = thread_count; i > 0; i--) {
		if (threads[i] >= 0) {
			sceKernelSuspendThread(threads[i]);
		}
	}
	suspended_count = thread_count;
}

void ResumeThreads() {
	if (suspended_count <= 0)
		return;
	int i;
	for (i = 0; i < thread_count; i++) {
		if (threads[i] >= 0) {
			sceKernelResumeThread(threads[i]);
		}
	}
	suspended_count = 0;
}
