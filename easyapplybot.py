from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
import logging
import os
import time
import random
import csv
import pandas as pd
import yaml

ChromeDriverManager = ChromeDriverManager

log = logging.getLogger(__name__)


def setupLogger() -> None:
    dt: str = datetime.strftime(datetime.now(), "%m_%d_%y %H_%M_%S ")

    if not os.path.isdir('./logs'):
        os.mkdir('./logs')

    logging.basicConfig(filename=('./logs/' + str(dt) + 'applyJobs.log'), filemode='w',
                        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s', datefmt='./logs/%d-%b-%y %H:%M:%S')
    log.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    c_handler.setFormatter(c_format)
    log.addHandler(c_handler)


class EasyApplyBot:
    setupLogger()
    MAX_SEARCH_TIME = 60 * 60

    def __init__(self, username, password, phone_number, salary, rate, uploads={}, filename='output.csv', blacklist=[], blackListTitles=[], experience_level=[]) -> None:
        log.info("Welcome to Easy Apply Bot")
        log.info("current directory is : " + os.getcwd())
        log.info("Please wait while we prepare the bot for you")

        self.uploads = uploads
        self.salary = salary
        self.rate = rate
        self.appliedJobIDs = self.get_appliedIDs(filename) or []
        self.filename = filename
        self.options = self.browser_options()
        self.browser = webdriver.Chrome(service=ChromeService(
            ChromeDriverManager().install()), options=self.options)
        self.wait = WebDriverWait(self.browser, 30)
        self.blacklist = blacklist
        self.blackListTitles = blackListTitles
        self.start_linkedin(username, password)
        self.phone_number = phone_number
        self.experience_level = experience_level

        self.locator = {
            "next": (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
            "review": (By.CSS_SELECTOR, "button[aria-label='Review your application']"),
            "submit": (By.CSS_SELECTOR, "button[aria-label='Submit application']"),
            "error": (By.CLASS_NAME, "artdeco-inline-feedback__message"),
            "upload_resume": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]"),
            "upload_cv": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]"),
            "follow": (By.CSS_SELECTOR, "label[for='follow-company-checkbox']"),
            "upload": (By.NAME, "file"),
            "search": (By.CLASS_NAME, "jobs-search-results-list"),
            "links": ("xpath", '//div[@data-job-id]'),
            "fields": (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping"),
            "radio_select": (By.CSS_SELECTOR, "input[type='radio']"),
            "multi_select": (By.XPATH, "//*[contains(@id, 'text-entity-list-form-component')]"),
            "text_select": (By.CLASS_NAME, "artdeco-text-input--input"),
            "2fa_oneClick": (By.ID, 'reset-password-submit-button'),
            "easy_apply_button": (By.XPATH, '//button[contains(@class, "jobs-apply-button")]')
        }

        self.qa_file = Path("qa.csv")
        self.answers = {}
        self.load_or_create_qa_file()

    def load_or_create_qa_file(self):
        if self.qa_file.is_file():
            df = pd.read_csv(self.qa_file)
            for index, row in df.iterrows():
                self.answers[row['Question']] = row['Answer']
        else:
            df = pd.DataFrame(columns=["Question", "Answer"])
            df.to_csv(self.qa_file, index=False, encoding='utf-8')

    def get_appliedIDs(self, filename) -> list | None:
        try:
            df = pd.read_csv(filename, header=None, names=[
                             'timestamp', 'jobID', 'job', 'company', 'attempted', 'result'], lineterminator='\n', encoding='utf-8')
            df['timestamp'] = pd.to_datetime(
                df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            jobIDs = list(df.jobID)
            log.info(f"{len(jobIDs)} jobIDs found")
            return jobIDs
        except Exception as e:
            log.info(f"{e} jobIDs could not be loaded from CSV {filename}")
            return None

    def browser_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-blink-features=AutomationControlled")
        return options

    def start_linkedin(self, username, password) -> None:
        log.info("Logging in.....Please wait :)")
        self.browser.get(
            "https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
        try:
            user_field = self.browser.find_element("id", "username")
            pw_field = self.browser.find_element("id", "password")
            login_button = self.browser.find_element(
                "xpath", '//*[@id="organic-div"]/form/div[3]/button')
            user_field.send_keys(username)
            user_field.send_keys(Keys.TAB)
            time.sleep(2)
            pw_field.send_keys(password)
            time.sleep(2)
            login_button.click()
            time.sleep(15)
        except TimeoutException:
            log.info(
                "TimeoutException! Username/password field or login button not found")

    def fill_data(self) -> None:
        self.browser.set_window_size(1, 1)
        self.browser.set_window_position(2000, 2000)

    def start_apply(self, positions, locations) -> None:
        start = time.time()
        self.fill_data()
        self.positions = positions
        self.locations = locations
        combos = [(position, location)
                  for position in positions for location in locations]
        random.shuffle(combos)
        for position, location in combos:
            if time.time() - start > self.MAX_SEARCH_TIME:
                break
            self.applications_loop(position, location)

    def applications_loop(self, position, location):
        count_application = 0
        count_job = 0
        jobs_per_page = 0
        start_time = time.time()

        log.info("Looking for jobs.. Please wait..")

        self.browser.set_window_position(1, 1)
        self.browser.maximize_window()
        self.browser, _ = self.next_jobs_page(
            position, location, jobs_per_page, experience_level=self.experience_level)
        log.info("Looking for jobs.. Please wait..")

        while time.time() - start_time < self.MAX_SEARCH_TIME:
            try:
                jobIDs = self.get_job_ids()
                self.apply_loop(jobIDs)
            except Exception as e:
                log.error(e)

    def get_job_ids(self):
        job_elements = self.get_elements("links")
        jobIDs = [job.get_attribute("data-job-id") for job in job_elements]
        return jobIDs

    def apply_loop(self, jobIDs):
        for jobID in jobIDs:
            if jobID not in self.appliedJobIDs:
                self.apply_to_job(jobID)

    def apply_to_job(self, jobID):
        self.get_job_page(jobID)
        time.sleep(1)
        button = self.get_easy_apply_button()
        if button:
            if any(word in self.browser.title for word in self.blackListTitles):
                log.info("Blacklisted title found, skipping job.")
            else:
                self.process_application(button, jobID)
        elif "You applied on" in self.browser.page_source:
            log.info("You have already applied to this position.")
        else:
            log.info("The Easy apply button does not exist.")
        self.write_to_file(button, jobID, self.browser.title,
                           button is not False)

    def process_application(self, button, jobID):
        button.click()
        self.fill_out_fields()
        self.send_resume()
        self.appliedJobIDs.append(jobID)

    def write_to_file(self, button, jobID, browserTitle, result) -> None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attempted = button is not False
        job = self.extract_text(browserTitle.split(' | ')[0])
        company = self.extract_text(browserTitle.split(' | ')[1])
        toWrite = [timestamp, jobID, job, company, attempted, result]
        with open(self.filename, 'a+') as f:
            writer = csv.writer(f)
            writer.writerow(toWrite)

    def extract_text(self, text):
        target = re.search(r"\(?\d?\)?\s?(\w.*)", text)
        return target.group(1) if target else text

    def get_job_page(self, jobID):
        job = f'https://www.linkedin.com/jobs/view/{jobID}'
        self.browser.get(job)
        self.job_page = self.load_page(sleep=0.5)
        return self.job_page

    def get_easy_apply_button(self):
        try:
            buttons = self.get_elements("easy_apply_button")
            for button in buttons:
                if button.is_displayed():
                    return button
        except Exception as e:
            log.debug("Easy Apply button not found")
        return False

    def fill_out_fields(self):
        fields = self.get_elements("fields")
        for field in fields:
            if "Mobile phone number" in field.text:
                field.find_element(By.TAG_NAME, "input").send_keys(
                    self.phone_number)

    def get_elements(self, type) -> list:
        element = self.locator[type]
        return self.browser.find_elements(element[0], element[1]) if self.is_present(element) else []

    def is_present(self, locator):
        return len(self.browser.find_elements(locator[0], locator[1])) > 0

    def send_resume(self) -> bool:
        try:
            next_locator = self.locator["next"]
            review_locator = self.locator["review"]
            submit_locator = self.locator["submit"]
            error_locator = self.locator["error"]
            upload_resume_locator = self.locator["upload_resume"]
            upload_cv_locator = self.locator["upload_cv"]
            follow_locator = self.locator["follow"]

            submitted = False
            loop = 0
            while loop < 2:
                if self.is_present(next_locator):
                    self.browser.find_element(*next_locator).click()
                elif self.is_present(review_locator):
                    self.browser.find_element(*review_locator).click()
                elif self.is_present(submit_locator):
                    self.browser.find_element(*submit_locator).click()
                    submitted = True
                    break
                elif self.is_present(error_locator):
                    log.error("Error in application form")
                    break
                loop += 1
        except Exception as e:
            log.error(e)
            log.error("cannot apply to this job")
        return submitted

    def process_questions(self):
        time.sleep(1)
        form = self.get_elements("fields")
        for field in form:
            question = field.text
            answer = self.ans_question(question.lower())
            if self.is_present(self.locator["radio_select"]):
                self.select_radio_option(answer)
            elif self.is_present(self.locator["multi_select"]):
                self.select_multi_option(answer)
            elif self.is_present(self.locator["text_select"]):
                self.fill_text_field(answer)

    def ans_question(self, question):
        predefined_answers = {
            "how many": "1",
            "experience": "1",
            "sponsor": "No",
            "do you": "Yes",
            "have you": "Yes",
            "US citizen": "Yes",
            "are you": "Yes",
            "salary": self.salary,
            "can you": "Yes",
            "gender": "Male",
            "race": "Wish not to answer",
            "lgbtq": "Wish not to answer",
            "ethnicity": "Wish not to answer",
            "nationality": "Wish not to answer",
            "government": "I do not wish to self-identify",
            "are you legally": "Yes"
        }
        answer = predefined_answers.get(
            question, "Not able to answer question automatically. Please provide answer")
        log.info(f"Answering question: {question} with answer: {answer}")
        if question not in self.answers:
            self.answers[question] = answer
            self.append_to_qa_file(question, answer)
        return answer

    def append_to_qa_file(self, question, answer):
        with open(self.qa_file, 'a') as f:
            writer = csv.writer(f)
            writer.writerow([question, answer])

    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script(f"window.scrollTo(0, {scroll_page});")
            scroll_page += 500
            time.sleep(0.1)
        time.sleep(sleep)
        return BeautifulSoup(self.browser.page_source, "lxml")

    def next_jobs_page(self, position, location, jobs_per_page, experience_level=[]):
        experience_level_str = ",".join(
            map(str, experience_level)) if experience_level else ""
        experience_level_param = f"&f_E={
            experience_level_str}" if experience_level_str else ""
        self.browser.get(f"https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords={
                         position}{location}&start={jobs_per_page}{experience_level_param}")
        log.info("Loading next job page?")
        self.load_page()
        return self.browser, jobs_per_page


if __name__ == '__main__':
    with open("config.yaml", 'r') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            log.error(exc)

    assert len(parameters['positions']) > 0
    assert len(parameters['locations']) > 0
    assert parameters['username'] is not None
    assert parameters['password'] is not None
    assert parameters['phone_number'] is not None

    if 'uploads' in parameters.keys() and type(parameters['uploads']) == list:
        raise Exception(
            "uploads read from the config file appear to be in list format while should be dict. Try removing '-' from line containing filename & path")

    log.info({k: parameters[k] for k in parameters.keys()
             if k not in ['username', 'password']})

    output_filename = parameters.get('output_filename', 'output.csv')
    blacklist = parameters.get('blacklist', [])
    blackListTitles = parameters.get('blackListTitles', [])
    uploads = parameters.get('uploads', {})
    locations = [l for l in parameters['locations'] if l is not None]
    positions = [p for p in parameters['positions'] if p is not None]

    bot = EasyApplyBot(parameters['username'], parameters['password'], parameters['phone_number'], parameters['salary'], parameters['rate'], uploads=uploads,
                       filename=output_filename, blacklist=blacklist, blackListTitles=blackListTitles, experience_level=parameters.get('experience_level', []))
    bot.start_apply(positions, locations)
