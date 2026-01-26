<script lang="ts">
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import i18n from '$lib/i18n';
	import { socket } from '$lib/stores';
	import { onDestroy, onMount } from 'svelte';

	interface GpuInfo {
		id: string;
		uuid: string;
		gpu_util: number;
		mem_total: number;
		mem_used: number;
		mem_free: number;
		driver: string;
		name: string;
		serial: string;
		display_mode: string;
		display_active: string;
		temperature: number;
	}
	const token = localStorage.token;
	let gpu_info: GpuInfo[] = [];
	const monitorHandler = async (event, cb) => {
		const type = event?.type ?? null;
		const data = event?.data ?? null;

		if (type === 'monitor:gpu') {
			gpu_info = data;
		}
	};

	onMount(async () => {
		$socket?.on('monitor', monitorHandler);

		await fetch(`${WEBUI_API_BASE_URL}/monitor/start`, {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${token}`
			}
		});
	});

	onDestroy(async () => {
		$socket?.off('monitor');
		await fetch(`${WEBUI_API_BASE_URL}/monitor/stop`, {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${token}`
			}
		});
	});
</script>

<div
	class="{gpu_info.length < 2
		? 'sm:grid-cols-1'
		: 'sm:grid-cols-2'} grid grid-cols-1 w-full h-full gap-2 auto-rows-min"
>
	{#each gpu_info as x (x.uuid)}
		<div class="flex bg-gray-800 rounded-lg h-24 p-2 items-center">
			<div class="flex-col w-16 h-16 flex justify-center">
				<p class="font-semibold text-lg">ID:</p>
				<p class="text-4xl font-bold mx-auto">{x.id}</p>
			</div>
			<div class="w-[1px] h-4/5 bg-white opacity-70" />
			<div class="flex flex-col ml-2 overflow-ellipsis whitespace-nowrap overflow-hidden">
				<p class="font-semibold text-md">
					{x.name}
				</p>
				<p>
					{$i18n.t('Used')}: {x.mem_used}/{x.mem_total} MB ({(x.mem_used / x.mem_total) * 100}%)
				</p>
				<p>{$i18n.t('Temperature')}: {x.temperature}°C</p>
			</div>
		</div>
	{/each}
</div>
