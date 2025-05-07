from string import ascii_letters as letters
from time import sleep, perf_counter
import ujson as ujs
import random
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.expected_conditions import visibility_of_element_located


def salary_into_dict(salary: str) -> dict:
    """
    Takes the string Indeed has for salary range, and parses it to return the data from it
    :param salary: String gotten from indeed scraping
    :return: Dictionary with the minimum pay, maximum pay, and pay period
    """
    period = salary[-5:].replace(' ', '')
    for i in range(len(letters)):
        salary = salary.replace(letters[i], '')

    salary = salary.replace('$', '').replace(',', '').replace(' ', '')
    # Checks if the remaining characters make up a range(22-28), or a single number(28), then returns the data from it
    if '-' in salary: return {
        'min': float(salary.split('-')[0]), 'max': float(salary.split('-')[1]), 'period': period
    }
    return {
        'min': float(salary.split('-')[0]), 'max': float(salary.split('-')[0]), 'period': period
    }


def get_all_job_postings(driver, job_keyword: str, location: str,
                               max_age: int = 14, jobs_dict: dict = None) -> tuple[dict, str]:
    """
    Make a request with the given url, and return the useful parts of the request

    There is a chance when it opens the tab, it will ask if you are human, press the box, there is a chance
    it will continually ask you over and over again, if it does, close the program, and rerun.

    :param driver: The webdriver object to use
    :param job_keyword: What to pass to indeed for the search, use '+' instead of spaces
    :param location: location for the jobs, must match what indeed uses in the url.
    :param max_age: Maximum age of job postings to get, must be 1, 3, 7, or 14
    :param jobs_dict: Dictionary of jobs already found for the job_keyword, if not passed, will make a new dict

    :return: The tuple of useful data received, (job_dict{...}, job_id)
    """
    last_page_num = 0
    start_time = time.perf_counter()
    # Raise an error if the given max age isn't valid
    if max_age not in [1, 3, 7, 14] and type(max_age) is int: raise ValueError
    url = 'https://www.indeed.com/jobs?q={}&l={}&sort=date&fromage={}&start={}'

    # Sleeps to pretend to be a real person not a bot, and opens the URL
    sleep(random.randint(2, 6))
    driver.get(url.format(job_keyword, location, max_age, 0))
    sleep(random.randint(8, 12))

    # Wait until page loads, long timeout for human user to check "Are you human" box
    wait = WebDriverWait(driver, timeout=120)
    wait.until(visibility_of_element_located((By.CLASS_NAME, 'jobsearch-JobCountAndSortPane-jobCount')))

    # Get the number of job results, to go page by page
    p = driver.find_element(by=By.CLASS_NAME, value='jobsearch-JobCountAndSortPane-jobCount').text
    max_iter_pgs = (int(p.split(' ')[0].replace('+', '').replace(',', '')) // 15) + 1

    if jobs_dict is None: jobs_dict = {}

    for i in range(max_iter_pgs):
        driver.get(url.format(job_keyword, location, max_age, i * 10))

        wait.until(visibility_of_element_located((By.ID, "mosaic-jobResults")))
        job_page = driver.find_element(By.ID, "mosaic-jobResults")

        # Current page number isn't saved as a class or id, so go through the data that contains the numbers and find it
        current_page_num = driver.find_element(By.XPATH, '/html/body/main/div/div[2]/div/div[5]/div/div[1]/nav/ul')
        page_number_elements = current_page_num.find_elements(By.XPATH, ".//*")
        for element in page_number_elements:
            if 'pagination-page-current' in element.get_attribute('innerHTML'):
                current_page_num = int(element.text)
                break

        # Make sure the current page value is an int, sometimes it's a bit funky for the first few pages
        # if it is funky, it will assume we have gone up another page, to avoid closing prematurely
        if type(current_page_num) is not int: current_page_num = last_page_num + 1

        # Checks if we went to a new page, if we didn't, that means we hit the end without realizing, break and move on
        if current_page_num <= last_page_num:
            break

        # Get the jobs on the current page
        jobs_in_page = job_page.find_elements(By.CLASS_NAME, "job_seen_beacon")
        for job in jobs_in_page:
            # Get salary or set to None if not provided, and get the other useful information, and save
            try:
                salary = job.find_element(By.CLASS_NAME, 'salary-snippet-container').text
                salary = salary_into_dict(salary)
            except NoSuchElementException:
                try:
                    salary = job.find_element(By.CLASS_NAME, 'estimated_salary').text
                    salary = salary_into_dict(salary)
                except NoSuchElementException:
                    salary = {'min': None, 'max': None, 'period': None}

            job_id = job.find_element(By.CSS_SELECTOR, 'a').get_attribute('id')
            jobs_dict[job_id] = {
                'job_id': job_id,
                'title': job.find_element(By.CLASS_NAME, 'jobTitle').text,
                'company': job.find_element(By.XPATH, '//*[@id="mosaic-provider-jobcards"]/ul/li[2]/div/div/div/div/div/div/table/tbody/tr/td[1]/div[2]/div/div[1]/span').text,
                'post_href': job.find_element(By.CSS_SELECTOR, 'a').get_attribute('href'),
                'salary_range': salary
            }
            last_page_num = current_page_num
    end_time = time.perf_counter()
    print(f'get_all_job_postings(...{job_keyword}, {location}...) finished in {end_time - start_time:.2f}s')
    return jobs_dict, job_keyword


def remove_duplicate_jobs(job_names: list[str]) -> None:
    """
    A function to go through the job files and remove any duplicates.
    It does this by going through each job in each file, checks if it has seen that job ID before
    If it does see that job ID, it deletes the entry it just found
    If it doesn't see the job ID, it saves it for future reference, and moves to the next

    :param job_names: A list of all the job names used to make the files, with + or _ instead of spaces
    :return: Doesn't return anything
    """
    basic_save_file = './data/bare_{}_data.json'
    used_job_ids = []
    for i in range(len(job_names)):
        with open(basic_save_file.format(job_names[i].replace('+', '_').lower())) as f:
            jobs_dict = ujs.load(f)
            job_id_keys = list(jobs_dict[job_names[i]].keys())
            for x in range(len(job_id_keys)):
                if job_id_keys[x] in used_job_ids:
                    del jobs_dict[job_names[i]][job_id_keys[x]]
                else:
                    used_job_ids.append(job_id_keys[x])

        with open(basic_save_file.format(job_names[i].replace('+', '_').lower()), 'w') as f:
            ujs.dump(jobs_dict, f)


# Function to get certain attributes like description, skills, requirements, and education, under development
#def get_job_attributes(driver, job_href: str) -> dict:
#    driver.get(job_href)
#    sleep(random.randint(2, 6))
#    wait = WebDriverWait(driver, timeout=120)
#    wait.until(visibility_of_element_located((By.ID, "jobDetailsSection")))
#    job_details_section = driver.find_element(By.ID, "jobDetailsSection")
#    job_profile_insights = driver.find_element(By.XPATH, '//*[@id="js-match-insights-provider"]/div/div/div/div[1]/div[2]')
#    print(job_profile_insights.text)


# This is also under development, will be changes heavily once there are more things I want to filter with
# Mainly waiting on myself to finish get_job_attributes() to finish this, for now it only filters on pay
# The reason im filtering for being below a certain pay, is because most higher paying jobs have requirements
#   that I just don't meet, I may miss out on some, but I will save a lot of time going through jobs, eventually
#   I will filter on the requirements themselves, but don't have that functionality yet.
def filter_print(job_names: list[str]):
    """
    Filter out jobs, currently only a set filter is applied, that will change in the future.
    :param job_names: List of all the job search names, with + or _ instead of spaces
    :return:
    """
    basic_save_file = './data/bare_{}_data.json'
    pay_not_provided = []
    for i in range(len(job_names)):
        print(basic_save_file.format(job_names[i].replace('+', '_').lower()))
        print(f'\n\n\n{job_names[i].replace("+", " ")} ----------------------------------------')
        with open(basic_save_file.format(job_names[i].replace('+', '_').lower())) as f:
            jobs_dict = ujs.load(f)
            job_id_keys = list(jobs_dict[job_names[i]].keys())
            for x in range(len(job_id_keys)):
                salary_min = jobs_dict[job_names[i]][job_id_keys[x]]['salary_range']['min']
                salary_max = jobs_dict[job_names[i]][job_id_keys[x]]['salary_range']['max']
                salary_period = jobs_dict[job_names[i]][job_id_keys[x]]['salary_range']['period']
                job_title = jobs_dict[job_names[i]][job_id_keys[x]]['title']
                job_href = jobs_dict[job_names[i]][job_id_keys[x]]['post_href']

                # Check if the jobs minimum pay is below a certain amount for each pay period, if it isn't, don't print
                # Putting each condition in 1 if statement may be a little faster, but readability would suck,
                #   so I decided to do it this way
                do_print = True
                if salary_period == 'hour' and salary_min > 25: do_print = False
                if salary_period == 'year' and salary_min > 52000: do_print = False
                if salary_period == 'month' and salary_min > 4400: do_print = False
                if salary_period == 'week' and salary_min > 1100: do_print = False
                # if no pay was provided, wait to print it till later
                if salary_min is None:
                    pay_not_provided.append([salary_min, salary_max, salary_period, job_title, job_href])
                    do_print = False

                if do_print: print(f'{salary_min}-{salary_max}/{salary_period} {job_title} - {job_href}')

    print('\n\n\n\nPAY NOT PROVIDED -------------------------------------------')
    for job in pay_not_provided:
        print(f'{job[0]}-{job[1]}/{job[2]} {job[3]} - {job[4]}')


def main(command: str):
    # The job searches to make
    job_keywords = [
        'junior+python+developer',
        'python+developer',
        'Python',
        'software+developer',
        'software+engineer',
        'IT+Helpdesk',
        'Help+Desk+Technician',
        'Tier+1+Technical+Support',
        'it+technical+support',
        'technical+support',
        'Tier+1+Support',
        'IT'
    ]
    # Locations to search, there is actually no functionality to use multiple locations yet however, but still
    # making it a list, so I remember to add it later
    location_keywords = ['Remote']
    basic_save_file = './data/bare_{}_data.json'

    if command == 'get_all_job_postings()':
        option = webdriver.ChromeOptions()
        option.add_argument("--disable-blink-features=AutomationControlled")
        option.add_experimental_option("excludeSwitches", ["enable-automation"])
        option.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=option)

        start_time_requests = perf_counter()
        print(f'running requests at {perf_counter() - start_time_main:.2f}s\n')
        for i in range(len(job_keywords)):
            # For each job, open the file and get the previous search results, or create the file and save an empty dict
            try:
                with open(basic_save_file.format(job_keywords[i].replace('+', '_').lower())) as f:
                    jobs_dict = ujs.load(f)[job_keywords[i]]

            except FileNotFoundError:
                with open(basic_save_file.format(job_keywords[i].replace('+', '_').lower()), 'x') as f:
                    ujs.dump({}, f)
                    jobs_dict = {}

            # Get the results for the job search, and save it to the file
            task_result_tuple = get_all_job_postings(
                driver=driver,
                job_keyword=job_keywords[i],
                location=location_keywords[0],
                jobs_dict=jobs_dict,
                max_age=3
            )
            with open(basic_save_file.format(job_keywords[i].replace('+', '_').lower()), 'w') as f:
                ujs.dump({task_result_tuple[1]: task_result_tuple[0]}, f)
        driver.quit()
        print(f'\nall requests finished at {perf_counter() - start_time_requests:.2f}s')

    elif command == 'remove_duplicate_jobs()':
        remove_duplicate_jobs(job_keywords)

#    elif command == 'get_job_attributes()':
#        option = webdriver.ChromeOptions()
#        option.add_argument("--disable-blink-features=AutomationControlled")
#        option.add_experimental_option("excludeSwitches", ["enable-automation"])
#        option.add_experimental_option("useAutomationExtension", False)
#
#        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=option)
#
#        for i in range(len(job_keywords)):
#            with open(basic_save_file.format(job_keywords[i].replace('+', '_').lower())) as f:
#                jobs_dict = ujs.load(f)
#                job_id_keys = list(jobs_dict[job_keywords[i]].keys())
#                for x in range(len(job_id_keys)):
#                    job_href = jobs_dict[job_keywords[i]][job_id_keys[x]]['post_href']
#                    get_job_attributes(driver, job_href)

    elif command =='filter_print()':
        filter_print(job_keywords)

if __name__ == '__main__':
    print('starting as __main__')
    input_val = input('')
    while input_val not in [
        'get_all_job_postings()',
        'remove_duplicate_jobs()',
        'get_job_attributes()',
        'filter_print()'
    ]: input_val = input('')
    start_time_main = time.perf_counter()
    main(command=input_val)
    print(f'__main__ finished in {time.perf_counter() - start_time_main:.2f}s')