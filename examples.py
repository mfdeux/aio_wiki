import asyncio
import signal
from contextlib import suppress

from aio_wiki import GraphClient, MediaClient

graph_client = GraphClient()
media_client = MediaClient()

word_list = ['adult', 'airplane', 'air', 'fan', 'fruit', 'home', 'nail', 'planet', 'software']


def signal_handler():
    print('Signal handler caught')
    tasks = [task for task in asyncio.Task.all_tasks() if task is not asyncio.Task.current_task()]
    for task in tasks:
        try:
            task.cancel()
        except RuntimeError:
            continue


async def main():
    cor = asyncio.ensure_future(graph_client.search_properties('instagram'))
    cor2 = asyncio.ensure_future(graph_client.sparql('''SELECT ?item WHERE {
            ?item rdfs:label "Google"@en
        }'''))
    tasks = [cor, cor2]
    for task in asyncio.as_completed(tasks):
        result = await task
        print('Task ret: {}'.format(result))


async def ping():
    with suppress(asyncio.CancelledError):
        await media_client.ping()


async def many():
    with suppress(asyncio.CancelledError):
        tasks = [asyncio.get_event_loop().create_task(ping()) for x in range(1, 100)]
        entity_tasks = []
        # results = await asyncio.gather(*tasks)
        # print(results)
        for index, task in enumerate(asyncio.as_completed(tasks)):
            result = await task
            print('SEARCH Task ret {}: {}'.format(index, result))
            # for item in result:
            #     entity_tasks.append(asyncio.ensure_future(graph_client.entity(item.get('id'))))
        # for index, task in enumerate(asyncio.as_completed(entity_tasks)):
        #     result = await task
        #     print('ENTITY Task ret {}: {}'.format(index, result))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    for sig in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, sig), signal_handler)
    try:
        loop.run_until_complete(main())
    except RuntimeError:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()
    # print(loop.run_until_complete(cor2))
