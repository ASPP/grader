# Grader: a command-line utility to grade applications

## Setup
### grader installation
  - Clone the repo https://github.com/ASPP/grader
  - [optional] create environment
  - [install] `pip install -e .`

### application data setup
  - Get access rights and URI from admin
  - Clone the ASPP organization repo, which includes the `applications` folder
  - Within this folder we expect at least two files:
      - `applications.csv`: this file is our *raw* data. It contains a CSV dump from the online application form. This is exported by admin at the appropriate time. This file never changes.
      - `applications.ini`: this file contains global configuration and the current state of the motivation grading process. Typically you do not touch this file manually. The initial setup is performed by the admin. Anything you do in grader, for example grading motivations, adding special labels to applicants, etc, is recorded in this file. You commit it and push it to share your progress with other reviewers. More about this file later.
  - You should have received a `criteria.txt` file with a list of grading criteria

### Test
Type `grader <DIR>`. This will start the grader interactive CLI.

If you get a bunch of info messages and a prompt, everything is set up correctly. 

`<DIR>` is the folder which contains the `applications.csv` and `applications.ini` files. If `<DIR>` is not specified, it is assumed to be the current folder. This is usually the `applications` subfolder in the ASPP organization clone on your machine.

## Quick Start for the impatient reviewer: grading applications
Grader is an interactive command line tool for reviewing ASPP applications, assigning scores and ranks to applicants, and extracting application stats.

  1. Start grader:
  ```
  $ grader -i your_name
  ```
  Note: `your_name` is lowercase without whitespace, e.g. `bob`.
  2. Start the motivation letter grading session, by entering the grading mode:
  ```
  grader> grade
  ```
  3. This will show you a motivation letter from the set of applicants that you haven't graded already, together with 
  some additional info
  4. The prompt will expect you to type one of the following:
      - `0, 1, -1` : your grade
      - `s` : to skip this applicant for now ➔ you will be able to grade it again after restarting the motivation grading in the next grading session
      - `b` : re-grade the previous motivation letter
      - `o` : add override (see below for details)
      - `d` : show the full detail about the current applicant
      - `l` : add a label to the current applicant (see below for details)
  6. After pressing enter the next motivation letter will be shown for you to grade
  7. To quit the grading mode, type `Ctrl+C`.
  8. By later quitting grader with the command `exit`, your gradings will be stored in the `applications.ini` file. Commit and push to share with the other reviewers. Push often.

Note 1: Unless you type `d`, the data shown is anonymized as far as possible to help you make unbiased decisions.

Note 2: Remeber that your changes are only saved locally, to make them permanent and visible to other reviewers, commit and push.

## Labelling applications
While in grading mode, you may want to label the current application, for example by setting the `OVERQUALIFIED` label. This marks the applicant as someone who is too much of an *expert* for ASPP. A list of commonly used labels can be found in the `criteria.txt` file.

When you want to add a label to an applicant, you type `l LABEL` at the grading prompt, where `LABEL` is the label you want to add. Note that grader has tab-completion on label names. 

## Use case: changing existing grades
  - You may want to re-grade a specific applicant. Enter grading mode like this:
    ```
    grader> grade Bob Smith
    ```
    Note that `grader` has tab-completion on applicant names.
  - You may want to re-grade/review all the motivation letters you graded with a specific grade, for example `-1`. Enter grading mode like this:
    ```
    grader> grade -g -1
    ```
 - You may want to re-grade/review all applicants with a specific label:
   ```
   grader> grade -l LABEL
   ```

## Use case: resolve disagreements
A *disagreement* between reviewer1 and reviewer2 is an applicant for whom the two reviewers gave diverging grades, e.g. `1` and `-1`. After grading all motivations, you may want to go through all disagreements with other reviewers to check if you simply made a typo or if you really disagree. In case of a real disagreement, a discussion among reviewers will be needed. To go through all disagreements with all other reviewers, enter grading mode with:

```
grader> grade -d
```

This will allow you to change or keep your grade for the corresponding motivation letter.

You can also solve disagreements with another reviewer, for example reviewer2, by:

```
grader> grade -d reviewer2
```

## Use case: setting overrides
While grading you may notice that an applicant has misjudge for example their Python proficiency, by self-rating as `novice/advanced-beginner`, when instead you judge them to be rather `competent/proficient`. In this case you should set an override for this field in their application. You type `o python` while in grading mode.

Note that in grading mode you have tab-completion on applicant fields. Once the field is auto-completed, by hitting `<tab>` again you'll get a list of possible values to select from. This will set a permanent override for this applicant in the `applications.ini`.

## Use case: ranking applications
After all reviewers have completed the motivation letter grading, it is possible to *rank* the applications. Each applicant gets a *score* calculated by evaluating a *formula*. 

You can get the formula used for ranking with: `grader> formula`.

You can visualize the ranking of the applicants with: `grader> rank`.

Highlanders will be visualized on top of other applicants.

## Use case: viewing individual applications
From the grader prompt you visualize applications by using the `dump` command. This allows you for example to visualize a subset of applications matching certain criteria. More details with `dump -h`.

For example, if you want to visualize all applicants with Italian nationality, you type:
```
grader> dump -a nationality Italy 
```

You can get a list of possible attributes with `dump -a list`.

## Use case: show stats
You can get some stats about applicants with the command `stat`. More details with `stat -h`.

## Use case: change the formula
You can experiment with effect of different weights in the formula on the applicant ranking by changing the formula as in this example:

```
grader> formula programming*0.2 + open_source*0.2
```

This will print the contributions of each factor to the final score of an applicant:

```
formula = programming*0.2 + open_source*0.2
score ∈ [ 0.000, 0.400]
applied ∈ [0, 1, 2]
contributions:
programming*0.2 : 50.0%
open_source*0.2 : 50.0%
```

By ranking the applicants using the `rank` command you will visualize the new ranking based on the new formula.

Note: the changes to the formula will be saved on exit. You are expected to rely on git to undo any changes, if desired.


## Advanced: admin use cases
## Advanced: getting lists
## Advanced: marking invitations/confirmations/declines
## Advanced: creating groups
## Advanced: create wiki pages
## Advanced: checklist before inviting (gender balance, nationality balance, same lab people, high motivations among invitees, enough git knowledge, enough Python proficiency)

## Glossary
### Common labels and their meaning
### Grading
### Grading mode
### Formula
### Scores
### Ranking
### Ratings
### Highlanders
