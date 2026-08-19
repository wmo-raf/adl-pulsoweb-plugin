test:
	docker compose -f docker-compose.dev.yml exec adl adl test --keepdb adl_pulsoweb_plugin.tests
