<script lang="ts">
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { socket } from '$lib/stores';
	import { onDestroy, onMount } from 'svelte';

	interface GpuInfo {
		id: number;
		uuid: string;
		gpu_util: number;
		mem_total: number;
		mem_used: number;
		mem_free: number;
		driver: string;
		gpu_name: string;
		serial: string;
		display_mode: string;
		display_active: string;
		temperature: number;
	}
	const token = localStorage.token;
	let gpu_info: GpuInfo[] = [];
	const monitorHandler = async (event, cb) => {
		console.log('AAAAAA', event);
		const type = event?.type ?? null;
		const data = event?.data ?? null;

		if (type === 'monitor:gpu') {
			const json_data = JSON.parse(data);
			gpu_info = json_data;
		}
	};

	onMount(async () => {
		$socket?.on('monitor', monitorHandler);

		await fetch(`${WEBUI_API_BASE_URL}/monitor/start`, {
			headers: {
				Authorization: `Bearer ${token}`
			}
		});
	});

	onDestroy(async () => {
		$socket?.off('monitor');
		await fetch(`${WEBUI_API_BASE_URL}/monitor/stop`, {
			headers: {
				Authorization: `Bearer ${token}`
			}
		});
	});
</script>

<div class="flex">
	{#each gpu_info as x}
		<div>x</div>
	{/each}
</div>
